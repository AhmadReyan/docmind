"""ARQ worker: the ``ingest_document`` task and worker settings.

``ingest_document`` is a plain async function so integration tests and the eval
harness can call it inline (``await ingest_document({}, str(doc_id))``) without a
worker process.
"""

import asyncio
import logging
import uuid
from collections.abc import Callable, Coroutine
from typing import Any, BinaryIO, ClassVar

from arq.connections import RedisSettings
from sqlalchemy import delete

from app.config import get_settings
from app.db import get_session_factory
from app.ingestion.chunking import chunk_pages
from app.ingestion.extract import extract_pages
from app.models import Chunk, Document
from app.providers.base import get_embedding_provider
from app.storage import Storage, get_storage

logger = logging.getLogger(__name__)

EMBED_BATCH_SIZE = 64


def _read_all(storage: Storage, path: str) -> bytes:
    handle: BinaryIO = storage.open(path)
    with handle:
        return handle.read()


async def ingest_document(ctx: dict[str, Any] | None, document_id: str) -> None:
    """Extract -> chunk -> embed -> mark ready (or failed with an error message)."""
    del ctx  # unused; present for ARQ's calling convention
    settings = get_settings()
    session_factory = get_session_factory()
    doc_uuid = uuid.UUID(document_id)
    async with session_factory() as session:
        document = await session.get(Document, doc_uuid)
        if document is None:
            logger.warning("ingest_document: document %s not found, skipping", document_id)
            return
        document.status = "processing"
        document.error_message = None
        await session.commit()
        try:
            storage = get_storage(settings)
            data = await asyncio.to_thread(_read_all, storage, document.storage_path)
            pages = extract_pages(data, document.mime_type)
            pieces = chunk_pages(pages)
            if not pieces:
                raise ValueError("Document contains no extractable text")

            # Idempotent re-ingest: drop any chunks from a previous attempt.
            await session.execute(delete(Chunk).where(Chunk.document_id == document.id))
            chunk_rows = [
                Chunk(
                    id=uuid.uuid4(),
                    document_id=document.id,
                    user_id=document.user_id,
                    chunk_index=index,
                    content=piece.content,
                    page_number=piece.page_number,
                    token_count=piece.token_count,
                )
                for index, piece in enumerate(pieces)
            ]
            session.add_all(chunk_rows)
            await session.flush()

            provider = get_embedding_provider(settings)
            for start in range(0, len(chunk_rows), EMBED_BATCH_SIZE):
                batch = chunk_rows[start : start + EMBED_BATCH_SIZE]
                vectors = await provider.embed([chunk.content for chunk in batch])
                for chunk, vector in zip(batch, vectors, strict=True):
                    chunk.embedding = vector

            document.page_count = len(pages)
            document.chunk_count = len(chunk_rows)
            document.status = "ready"
            await session.commit()
            logger.info(
                "ingest_document: %s ready (%d pages, %d chunks)",
                document_id,
                len(pages),
                len(chunk_rows),
            )
        except Exception as exc:
            logger.exception("ingest_document: %s failed", document_id)
            await session.rollback()
            failed = await session.get(Document, doc_uuid)
            if failed is not None:
                failed.status = "failed"
                failed.error_message = str(exc)[:1000]
                await session.commit()


class WorkerSettings:
    """ARQ worker settings; run with ``arq app.ingestion.worker.WorkerSettings``."""

    functions: ClassVar[list[Callable[..., Coroutine[Any, Any, None]]]] = [ingest_document]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 4
    job_timeout = 600

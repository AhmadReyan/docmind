"""Document endpoints: upload (enqueues ingestion), list, detail, chunks, delete."""

import asyncio
import uuid
from pathlib import PurePosixPath
from typing import Annotated

from fastapi import APIRouter, File, UploadFile, status
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select

from app.api.deps import ArqPoolDep, CurrentUser, PaginationDep, SessionDep, SettingsDep
from app.core import rate_limit
from app.core.errors import ApiError
from app.models import Chunk, Document
from app.schemas.common import Page
from app.schemas.documents import ChunkOut, DocumentOut
from app.storage import build_storage_path, get_storage

router = APIRouter(prefix="/api/documents", tags=["documents"])

# Canonical mime type per allowed extension (what we store on the Document row).
_EXTENSION_MIME = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".md": "text/markdown",
}
# Client-declared content types accepted for each extension. Browsers are sloppy
# (octet-stream, text/x-markdown, md served as text/plain), so accept those too.
_ACCEPTED_CONTENT_TYPES = {
    ".pdf": {"application/pdf", "application/x-pdf", "application/octet-stream"},
    ".txt": {"text/plain", "application/octet-stream"},
    ".md": {"text/markdown", "text/x-markdown", "text/plain", "application/octet-stream"},
}

INGEST_JOB_NAME = "ingest_document"


def _not_found() -> ApiError:
    return ApiError(status.HTTP_404_NOT_FOUND, "Document not found", "not_found")


async def _get_owned_document(
    session: SessionDep, user_id: uuid.UUID, document_id: uuid.UUID
) -> Document:
    document = await session.scalar(
        select(Document).where(Document.id == document_id, Document.user_id == user_id)
    )
    if document is None:
        raise _not_found()
    return document


@router.post("", response_model=DocumentOut, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    file: Annotated[UploadFile, File()],
    user: CurrentUser,
    session: SessionDep,
    settings: SettingsDep,
    pool: ArqPoolDep,
) -> Document:
    allowed = await rate_limit.hit(
        pool, rate_limit.upload_key(user.id), settings.upload_rate_limit_per_hour, 3600
    )
    if not allowed:
        raise ApiError(status.HTTP_429_TOO_MANY_REQUESTS, "Upload limit reached", "rate_limited")

    filename = file.filename or ""
    ext = PurePosixPath(filename).suffix.lower()
    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if ext not in _EXTENSION_MIME or (
        content_type and content_type not in _ACCEPTED_CONTENT_TYPES[ext]
    ):
        raise ApiError(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "Only PDF, TXT and Markdown files are supported",
            "unsupported_file_type",
        )

    data = await file.read()
    if len(data) > settings.max_upload_bytes:
        raise ApiError(
            413,  # Content Too Large (constant name differs across starlette versions)
            f"File exceeds the {settings.max_upload_bytes // (1024 * 1024)} MB limit",
            "file_too_large",
        )

    document_id = uuid.uuid4()
    storage_path = build_storage_path(user.id, document_id, ext)
    storage = get_storage(settings)
    await asyncio.to_thread(storage.save, storage_path, data)

    document = Document(
        id=document_id,
        user_id=user.id,
        title=PurePosixPath(filename).stem,
        filename=filename,
        mime_type=_EXTENSION_MIME[ext],
        size_bytes=len(data),
        storage_path=storage_path,
        status="pending",
    )
    session.add(document)
    await session.commit()
    await session.refresh(document)

    await pool.enqueue_job(INGEST_JOB_NAME, str(document_id))
    return document


@router.get("", response_model=Page[DocumentOut])
async def list_documents(
    user: CurrentUser, session: SessionDep, pagination: PaginationDep
) -> Page[DocumentOut]:
    total = await session.scalar(
        select(func.count()).select_from(Document).where(Document.user_id == user.id)
    )
    rows = await session.scalars(
        select(Document)
        .where(Document.user_id == user.id)
        .order_by(Document.created_at.desc(), Document.id.desc())
        .limit(pagination.limit)
        .offset(pagination.offset)
    )
    return Page(items=[DocumentOut.model_validate(document) for document in rows], total=total or 0)


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(document_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> Document:
    return await _get_owned_document(session, user.id, document_id)


@router.get("/{document_id}/chunks", response_model=Page[ChunkOut])
async def list_chunks(
    document_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    pagination: PaginationDep,
) -> Page[ChunkOut]:
    document = await _get_owned_document(session, user.id, document_id)
    total = await session.scalar(
        select(func.count()).select_from(Chunk).where(Chunk.document_id == document.id)
    )
    rows = await session.scalars(
        select(Chunk)
        .where(Chunk.document_id == document.id)
        .order_by(Chunk.chunk_index.asc())
        .limit(pagination.limit)
        .offset(pagination.offset)
    )
    return Page(items=[ChunkOut.model_validate(chunk) for chunk in rows], total=total or 0)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    settings: SettingsDep,
) -> None:
    document = await _get_owned_document(session, user.id, document_id)
    storage = get_storage(settings)
    await asyncio.to_thread(storage.delete, document.storage_path)
    # Core DELETE so the database-level ON DELETE CASCADE removes chunks in one pass.
    await session.execute(sa_delete(Document).where(Document.id == document.id))
    await session.commit()

"""Hybrid retrieval: pgvector cosine + Postgres full-text, fused with RRF (k=60)."""

import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import Float, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Chunk, Document
from app.providers.base import EmbeddingProvider

RRF_K = 60
CANDIDATE_LIMIT = 20


@dataclass
class ScoredChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    chunk_index: int
    content: str
    page_number: int | None
    score: float  # RRF fusion score


def rrf_fuse(rankings: Sequence[Sequence[uuid.UUID]], *, k: int = RRF_K) -> dict[uuid.UUID, float]:
    """Reciprocal Rank Fusion: score(id) = sum over rankings of 1 / (k + rank)."""
    scores: dict[uuid.UUID, float] = defaultdict(float)
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] += 1.0 / (k + rank)
    return dict(scores)


async def retrieve(
    session: AsyncSession,
    user_id: uuid.UUID,
    query: str,
    *,
    embedding_provider: EmbeddingProvider,
    top_k: int = 6,
) -> list[ScoredChunk]:
    """Retrieve the user's top_k chunks for a query via hybrid vector+keyword search."""
    query_vec = (await embedding_provider.embed([query]))[0]

    vector_stmt = (
        select(Chunk.id)
        .where(Chunk.user_id == user_id, Chunk.embedding.is_not(None))
        .order_by(Chunk.embedding.op("<=>", return_type=Float)(query_vec))
        .limit(CANDIDATE_LIMIT)
    )
    vector_ids: list[uuid.UUID] = list(await session.scalars(vector_stmt))

    tsquery = func.websearch_to_tsquery("english", query)
    keyword_stmt = (
        select(Chunk.id)
        .where(Chunk.user_id == user_id, Chunk.content_tsv.op("@@")(tsquery))
        .order_by(func.ts_rank_cd(Chunk.content_tsv, tsquery).desc(), Chunk.id)
        .limit(CANDIDATE_LIMIT)
    )
    keyword_ids: list[uuid.UUID] = list(await session.scalars(keyword_stmt))

    fused = rrf_fuse([vector_ids, keyword_ids])
    if not fused:
        return []
    # Deterministic tie-break on id so results are stable across runs.
    top = sorted(fused.items(), key=lambda item: (-item[1], str(item[0])))[:top_k]
    top_ids = [chunk_id for chunk_id, _score in top]

    rows = await session.execute(
        select(Chunk, Document.title)
        .join(Document, Chunk.document_id == Document.id)
        .where(Chunk.id.in_(top_ids))
    )
    by_id: dict[uuid.UUID, tuple[Chunk, str]] = {
        chunk.id: (chunk, title) for chunk, title in rows.tuples()
    }
    results: list[ScoredChunk] = []
    for chunk_id, score in top:
        entry = by_id.get(chunk_id)
        if entry is None:  # pragma: no cover - deleted between queries
            continue
        chunk, title = entry
        results.append(
            ScoredChunk(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                document_title=title,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                page_number=chunk.page_number,
                score=score,
            )
        )
    return results

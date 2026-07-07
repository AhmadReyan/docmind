"""RAG orchestration: retrieve -> build sources -> prompt -> stream LLM deltas.

Yields structured events; the API layer (app/api/chat.py) converts them to SSE and
handles persistence plus the terminal ``done``/``error`` events.
"""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.providers.base import ChatMessage, EmbeddingProvider, LLMProvider
from app.rag.prompts import build_messages
from app.rag.retrieval import retrieve
from app.schemas.chat import Source

SNIPPET_LENGTH = 200


@dataclass(frozen=True)
class SourcesEvent:
    sources: list[Source]


@dataclass(frozen=True)
class TokenEvent:
    delta: str


PipelineEvent = SourcesEvent | TokenEvent


async def answer_question(
    session: AsyncSession,
    user_id: uuid.UUID,
    question: str,
    history: list[ChatMessage],
    *,
    embedding_provider: EmbeddingProvider,
    llm_provider: LLMProvider,
    top_k: int = 6,
) -> AsyncIterator[PipelineEvent]:
    chunks = await retrieve(
        session, user_id, question, embedding_provider=embedding_provider, top_k=top_k
    )
    sources = [
        Source(
            index=i,
            chunk_id=chunk.chunk_id,
            document_id=chunk.document_id,
            document_title=chunk.document_title,
            page_number=chunk.page_number,
            snippet=chunk.content[:SNIPPET_LENGTH],
            score=chunk.score,
        )
        for i, chunk in enumerate(chunks, start=1)
    ]
    yield SourcesEvent(sources=sources)
    messages = build_messages(question, chunks, history)
    async for delta in llm_provider.generate_stream(messages):
        yield TokenEvent(delta=delta)

"""Unit tests for the deterministic extractive answerer (with hash embeddings)."""

import uuid

from app.providers.base import ChatMessage, LLMProvider
from app.providers.hashing import HashEmbeddingProvider
from app.providers.local import LocalLLMProvider
from app.rag.prompts import build_messages
from app.rag.retrieval import ScoredChunk


def make_chunk(title: str, content: str, page_number: int | None = None) -> ScoredChunk:
    return ScoredChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title=title,
        chunk_index=0,
        content=content,
        page_number=page_number,
        score=0.02,
    )


async def _collect(provider: LocalLLMProvider, messages: list[ChatMessage]) -> str:
    return "".join([delta async for delta in provider.generate_stream(messages)])


async def test_extractive_answer_has_citation_markers() -> None:
    chunks = [
        make_chunk("Sky Facts", "The sky appears blue due to Rayleigh scattering.", 2),
        make_chunk("Ocean Facts", "The ocean is salty because of dissolved minerals."),
    ]
    messages = build_messages("Why is the sky blue?", chunks, [])
    provider = LocalLLMProvider(embedding_provider=HashEmbeddingProvider())
    answer = await _collect(provider, messages)
    assert answer.startswith("Based on your documents")
    assert "[1]" in answer or "[2]" in answer
    # The best sentence shares tokens with the question, so block [1] must be cited.
    assert "Rayleigh scattering. [1]" in answer


async def test_sentences_ordered_by_block_then_position() -> None:
    chunks = [
        make_chunk("Doc A", "Alpha fact one. Alpha fact two."),
        make_chunk("Doc B", "Beta fact one."),
    ]
    messages = build_messages("alpha beta fact", chunks, [])
    provider = LocalLLMProvider(embedding_provider=HashEmbeddingProvider())
    answer = await _collect(provider, messages)
    assert answer.index("[1]") < answer.index("[2]")


async def test_no_context_blocks_yields_fallback_message() -> None:
    messages = build_messages("Anything at all?", [], [])
    provider = LocalLLMProvider(embedding_provider=HashEmbeddingProvider())
    answer = await _collect(provider, messages)
    assert "couldn't find relevant information" in answer


async def test_streams_multiple_deltas() -> None:
    chunks = [make_chunk("Doc", "One short sentence about testing.")]
    messages = build_messages("testing?", chunks, [])
    provider = LocalLLMProvider(embedding_provider=HashEmbeddingProvider())
    deltas = [delta async for delta in provider.generate_stream(messages)]
    assert len(deltas) > 3  # word-by-word streaming
    assert "".join(deltas) == "".join(deltas).strip()


def test_protocol_compliance() -> None:
    provider = LocalLLMProvider(embedding_provider=HashEmbeddingProvider())
    assert isinstance(provider, LLMProvider)
    assert provider.name == "local"

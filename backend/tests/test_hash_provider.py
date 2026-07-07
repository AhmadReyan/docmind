"""Unit tests for the deterministic hash embedding provider."""

import math

from app.providers.base import EmbeddingProvider
from app.providers.hashing import HashEmbeddingProvider


async def test_determinism_across_instances() -> None:
    first = await HashEmbeddingProvider().embed(["the quick brown fox", "hello"])
    second = await HashEmbeddingProvider().embed(["the quick brown fox", "hello"])
    assert first == second


async def test_dimension_and_normalization() -> None:
    provider = HashEmbeddingProvider()
    assert provider.dimension == 384
    (vec,) = await provider.embed(["some document text"])
    assert len(vec) == 384
    assert math.isclose(math.sqrt(sum(x * x for x in vec)), 1.0, rel_tol=1e-9)


async def test_different_texts_get_different_vectors() -> None:
    provider = HashEmbeddingProvider()
    a, b = await provider.embed(["completely different words", "unrelated sentence tokens"])
    assert a != b


async def test_token_overlap_increases_similarity() -> None:
    provider = HashEmbeddingProvider()
    query, close, far = await provider.embed(
        ["docmind retrieval engine", "docmind retrieval pipeline", "banana smoothie recipe"]
    )
    sim_close = sum(x * y for x, y in zip(query, close, strict=True))
    sim_far = sum(x * y for x, y in zip(query, far, strict=True))
    assert sim_close > sim_far


async def test_empty_text_is_safe_and_deterministic() -> None:
    provider = HashEmbeddingProvider()
    first, second = await provider.embed(["", ""])
    assert first == second
    assert len(first) == 384


def test_protocol_compliance() -> None:
    provider = HashEmbeddingProvider()
    assert isinstance(provider, EmbeddingProvider)
    assert provider.name == "hash"

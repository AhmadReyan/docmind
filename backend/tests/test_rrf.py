"""Unit tests for Reciprocal Rank Fusion math."""

import uuid

import pytest

from app.rag.retrieval import rrf_fuse


def test_rrf_scores_exact_values() -> None:
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    scores = rrf_fuse([[a, b], [b, c]], k=60)
    assert scores[a] == pytest.approx(1 / 61)
    assert scores[b] == pytest.approx(1 / 62 + 1 / 61)
    assert scores[c] == pytest.approx(1 / 62)


def test_rrf_item_in_both_lists_outranks_single_list_leader() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    scores = rrf_fuse([[a, b], [b]], k=60)
    assert scores[b] > scores[a]


def test_rrf_empty_rankings() -> None:
    assert rrf_fuse([]) == {}
    assert rrf_fuse([[], []]) == {}


def test_rrf_custom_k() -> None:
    a = uuid.uuid4()
    assert rrf_fuse([[a]], k=1)[a] == pytest.approx(1 / 2)

"""Unit tests for the recursive chunker's invariants."""

import itertools

from app.ingestion.chunking import (
    OVERLAP_TOKENS,
    TARGET_TOKENS,
    chunk_pages,
    estimate_tokens,
)
from app.ingestion.extract import Page


def _long_text(sentences: int) -> str:
    return " ".join(
        f"Sentence number {i} talks about topic {i % 7} in moderate detail."
        for i in range(sentences)
    )


def test_estimate_tokens_heuristic() -> None:
    assert estimate_tokens("") == 1  # minimum
    assert estimate_tokens("a" * 400) == 100


def test_short_page_single_chunk_carries_page_number() -> None:
    chunks = chunk_pages([Page(text="Hello world. This is short.", page_number=3)])
    assert len(chunks) == 1
    assert chunks[0].page_number == 3
    assert chunks[0].content == "Hello world. This is short."
    assert chunks[0].token_count == estimate_tokens(chunks[0].content)


def test_no_empty_chunks_for_whitespace_page() -> None:
    assert chunk_pages([Page(text="   \n\n  \t ", page_number=1)]) == []
    assert chunk_pages([Page(text="", page_number=None)]) == []


def test_long_document_splits_with_size_bounds() -> None:
    chunks = chunk_pages([Page(text=_long_text(300), page_number=None)])
    assert len(chunks) > 1
    max_tokens = TARGET_TOKENS + OVERLAP_TOKENS + 2  # packing allows tail + one atom
    for chunk in chunks:
        assert chunk.content.strip()
        assert 0 < chunk.token_count <= max_tokens


def test_consecutive_chunks_overlap() -> None:
    chunks = chunk_pages([Page(text=_long_text(300), page_number=None)])
    assert len(chunks) > 2
    for previous, current in itertools.pairwise(chunks):
        # The next chunk starts with the word-aligned tail of the previous chunk.
        assert current.content[:15] in previous.content


def test_page_numbers_carried_across_pages_and_never_mixed() -> None:
    pages = [
        Page(text=_long_text(150), page_number=1),
        Page(text=_long_text(150), page_number=2),
    ]
    chunks = chunk_pages(pages)
    page_numbers = {chunk.page_number for chunk in chunks}
    assert page_numbers == {1, 2}
    # Order is stable: all page-1 chunks come before page-2 chunks.
    first_page_two = next(i for i, c in enumerate(chunks) if c.page_number == 2)
    assert all(c.page_number == 1 for c in chunks[:first_page_two])


def test_paragraph_boundaries_preferred() -> None:
    text = "First paragraph here.\n\nSecond paragraph here."
    chunks = chunk_pages([Page(text=text, page_number=None)])
    assert len(chunks) == 1
    assert chunks[0].content == "First paragraph here.\n\nSecond paragraph here."


def test_hard_cut_of_pathological_unbroken_text() -> None:
    text = "x" * 10_000  # no paragraphs, no sentences, no spaces
    chunks = chunk_pages([Page(text=text, page_number=None)])
    assert len(chunks) > 1
    assert all(chunk.content.strip() for chunk in chunks)


def test_chunking_is_deterministic() -> None:
    pages = [Page(text=_long_text(200), page_number=1)]
    assert chunk_pages(pages) == chunk_pages(pages)

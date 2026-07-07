"""Recursive text chunking: ~450-token chunks with ~60-token overlap.

Token counting uses the dependency-free, deterministic ``len(text) // 4`` heuristic
(chosen over a whitespace-based estimate because it is monotonic in character
length, which makes the character budgets below exact). Split priority within a
page: paragraphs -> sentences -> hard character cut. Chunks never span pages, so
``page_number`` is always unambiguous, and empty/whitespace chunks are never
emitted. Consecutive chunks from the same page share a ~60-token tail/head overlap.
"""

import re
from dataclasses import dataclass

from app.ingestion.extract import Page

TARGET_TOKENS = 450
OVERLAP_TOKENS = 60
_CHARS_PER_TOKEN = 4

_PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def estimate_tokens(text: str) -> int:
    """Deterministic token estimate: ~4 characters per token, minimum 1."""
    return max(1, len(text) // _CHARS_PER_TOKEN)


@dataclass(frozen=True)
class TextChunk:
    content: str
    page_number: int | None
    token_count: int


def chunk_pages(
    pages: list[Page],
    *,
    target_tokens: int = TARGET_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
) -> list[TextChunk]:
    """Chunk extracted pages. Order is stable: page order, then position within page."""
    budget_chars = target_tokens * _CHARS_PER_TOKEN
    overlap_chars = overlap_tokens * _CHARS_PER_TOKEN
    chunks: list[TextChunk] = []
    for page in pages:
        for content in _chunk_text(page.text, budget_chars, overlap_chars):
            chunks.append(
                TextChunk(
                    content=content,
                    page_number=page.page_number,
                    token_count=estimate_tokens(content),
                )
            )
    return chunks


def _chunk_text(text: str, budget_chars: int, overlap_chars: int) -> list[str]:
    pieces = _atomize(text, budget_chars)
    if not pieces:
        return []
    chunks: list[str] = []
    current = ""
    for piece, joiner in pieces:
        candidate = f"{current}{joiner}{piece}" if current else piece
        if len(candidate) <= budget_chars:
            current = candidate
            continue
        chunks.append(current)
        tail = _overlap_tail(current, overlap_chars)
        current = f"{tail} {piece}" if tail else piece
    if current.strip():
        chunks.append(current)
    return chunks


def _atomize(text: str, budget_chars: int) -> list[tuple[str, str]]:
    """Split text into non-empty pieces each <= budget, tagged with their join separator.

    Paragraphs join with a blank line; sentence/hard-cut fragments join with a space.
    """
    pieces: list[tuple[str, str]] = []
    for paragraph in _PARAGRAPH_SPLIT_RE.split(text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if len(paragraph) <= budget_chars:
            pieces.append((paragraph, "\n\n"))
            continue
        for raw_sentence in _SENTENCE_SPLIT_RE.split(paragraph):
            sentence = raw_sentence.strip()
            if not sentence:
                continue
            if len(sentence) <= budget_chars:
                pieces.append((sentence, " "))
                continue
            for start in range(0, len(sentence), budget_chars):
                fragment = sentence[start : start + budget_chars].strip()
                if fragment:
                    pieces.append((fragment, " "))
    return pieces


def _overlap_tail(text: str, overlap_chars: int) -> str:
    """Last ~overlap_chars of a chunk, trimmed forward to a word boundary."""
    if overlap_chars <= 0:
        return ""
    if len(text) <= overlap_chars:
        return text.strip()
    tail = text[-overlap_chars:]
    space = tail.find(" ")
    if space != -1:
        tail = tail[space + 1 :]
    return tail.strip()

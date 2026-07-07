"""Zero-API-key providers: fastembed embeddings + a deterministic extractive answerer.

``LocalLLMProvider`` is not a language model: it parses the numbered context blocks
out of the final user prompt (format defined by ``app.rag.prompts``), scores each
context sentence against the question with the *configured* embedding provider
(injectable so tests run on hash embeddings with no model download), stitches the
best sentences into a cited answer, and streams it word by word.
"""

import asyncio
import math
import re
import threading
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from app.models import EMBEDDING_DIM
from app.providers.base import ChatMessage, EmbeddingProvider

if TYPE_CHECKING:
    from fastembed import TextEmbedding

_FASTEMBED_MODEL_NAME = "BAAI/bge-small-en-v1.5"

_model: "TextEmbedding | None" = None
_model_lock = threading.Lock()


def _load_model() -> "TextEmbedding":
    """Load the fastembed model once per process (thread-safe, lazy)."""
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                from fastembed import TextEmbedding

                _model = TextEmbedding(model_name=_FASTEMBED_MODEL_NAME)
    return _model


class LocalEmbeddingProvider:
    name = "local"
    dimension = EMBEDDING_DIM

    async def embed(self, texts: list[str]) -> list[list[float]]:
        # fastembed is synchronous (ONNX runtime); keep the event loop free.
        return await asyncio.to_thread(self._embed_sync, texts)

    def _embed_sync(self, texts: list[str]) -> list[list[float]]:
        model = _load_model()
        return [_normalize([float(x) for x in vec]) for vec in model.embed(texts)]


def _normalize(vec: list[float]) -> list[float]:
    norm = sum(x * x for x in vec) ** 0.5
    if norm == 0.0:
        return vec
    return [x / norm for x in vec]


# Matches the context-block headers produced by app.rag.prompts.format_source_header:
# "[1] (Some Title, p.3)" or "[2] (Some Title)" on their own line.
_BLOCK_HEADER_RE = re.compile(r"^\[(\d+)\] \(.*\)$", re.MULTILINE)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

_MAX_SENTENCES = 5
_STREAM_DELAY_SECONDS = 0.015

_NO_CONTEXT_ANSWER = (
    "I couldn't find relevant information in your documents. "
    "Try uploading a relevant document or rephrasing your question."
)


class LocalLLMProvider:
    """Deterministic extractive answerer over the RAG prompt's context blocks."""

    name = "local"

    def __init__(self, embedding_provider: EmbeddingProvider | None = None) -> None:
        self._embedding_provider = embedding_provider

    def _resolve_embedding_provider(self) -> EmbeddingProvider:
        if self._embedding_provider is None:
            from app.config import get_settings
            from app.providers.base import get_embedding_provider

            self._embedding_provider = get_embedding_provider(get_settings())
        return self._embedding_provider

    async def generate_stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> AsyncIterator[str]:
        del temperature, max_tokens  # deterministic; parameters are irrelevant
        prompt = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"),
            "",
        )
        question, blocks = _parse_prompt(prompt)
        answer = _NO_CONTEXT_ANSWER
        if blocks:
            selected = await self._select_sentences(question, blocks)
            if selected:
                cited = " ".join(
                    f"{sentence.rstrip()} [{block_index}]" for block_index, sentence in selected
                )
                answer = f"Based on your documents, here is what I found. {cited}"
        for i, word in enumerate(answer.split()):
            yield word if i == 0 else f" {word}"
            await asyncio.sleep(_STREAM_DELAY_SECONDS)

    async def _select_sentences(
        self, question: str, blocks: list[tuple[int, str]]
    ) -> list[tuple[int, str]]:
        """Pick the top sentences by cosine similarity, ordered by (block, position)."""
        candidates: list[tuple[int, int, str]] = []  # (block_index, position, sentence)
        for block_index, text in blocks:
            for position, raw in enumerate(_SENTENCE_SPLIT_RE.split(text)):
                sentence = raw.strip()
                if sentence:
                    candidates.append((block_index, position, sentence))
        if not candidates:
            return []
        provider = self._resolve_embedding_provider()
        vectors = await provider.embed([question] + [c[2] for c in candidates])
        query_vec, sentence_vecs = vectors[0], vectors[1:]
        scored = sorted(
            zip(candidates, sentence_vecs, strict=True),
            key=lambda pair: _cosine(query_vec, pair[1]),
            reverse=True,
        )
        chosen: list[tuple[int, int, str]] = []
        seen: set[str] = set()
        for (block_index, position, sentence), _vec in scored:
            key = sentence.lower()
            if key in seen:
                continue
            seen.add(key)
            chosen.append((block_index, position, sentence))
            if len(chosen) >= _MAX_SENTENCES:
                break
        chosen.sort(key=lambda item: (item[0], item[1]))
        return [(block_index, sentence) for block_index, _position, sentence in chosen]


def _parse_prompt(prompt: str) -> tuple[str, list[tuple[int, str]]]:
    """Split the RAG user prompt into (question, [(block_index, block_text), ...])."""
    sources_part, _, question_part = prompt.rpartition("\nQuestion:")
    if not _:
        return prompt.strip(), []
    question = question_part.strip()
    headers = list(_BLOCK_HEADER_RE.finditer(sources_part))
    blocks: list[tuple[int, str]] = []
    for i, match in enumerate(headers):
        end = headers[i + 1].start() if i + 1 < len(headers) else len(sources_part)
        text = sources_part[match.end() : end].strip()
        if text:
            blocks.append((int(match.group(1)), text))
    return question, blocks


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)

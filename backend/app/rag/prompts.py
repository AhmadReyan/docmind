"""Prompt assembly for the RAG pipeline.

The context-block format is a mini-contract with ``LocalLLMProvider``, which parses
it back out of the final user message:

    Sources:
    [1] (Doc Title, p.3)
    <chunk text>

    [2] (Other Doc)
    <chunk text>

    Question: <question>
"""

from app.providers.base import ChatMessage
from app.rag.retrieval import ScoredChunk

MAX_HISTORY_MESSAGES = 6

SYSTEM_PROMPT = (
    "You are DocMind, a document question-answering assistant. Answer using ONLY the "
    "numbered sources provided in the user message. Cite every claim by appending the "
    "matching [n] marker after the sentence it supports. Do not use outside knowledge. "
    "If the sources do not contain enough information to answer, say so plainly."
)


def format_source_header(index: int, title: str, page_number: int | None) -> str:
    if page_number is not None:
        return f"[{index}] ({title}, p.{page_number})"
    return f"[{index}] ({title})"


def build_context(chunks: list[ScoredChunk]) -> str:
    """Numbered context blocks; block [n] corresponds to Source.index == n (1-based)."""
    blocks = [
        f"{format_source_header(i, chunk.document_title, chunk.page_number)}\n"
        f"{chunk.content.strip()}"
        for i, chunk in enumerate(chunks, start=1)
    ]
    return "\n\n".join(blocks)


def build_messages(
    question: str,
    chunks: list[ScoredChunk],
    history: list[ChatMessage],
) -> list[ChatMessage]:
    """System prompt + last 6 conversation messages + sources-and-question user message."""
    context = build_context(chunks) if chunks else "(no sources found)"
    user_prompt = f"Sources:\n{context}\n\nQuestion: {question}"
    messages: list[ChatMessage] = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history[-MAX_HISTORY_MESSAGES:])
    messages.append({"role": "user", "content": user_prompt})
    return messages

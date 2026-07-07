"""Unit tests for prompt/citation assembly."""

import uuid

from app.providers.base import ChatMessage
from app.rag.prompts import MAX_HISTORY_MESSAGES, SYSTEM_PROMPT, build_messages
from app.rag.retrieval import ScoredChunk


def make_chunk(title: str, content: str, page_number: int | None) -> ScoredChunk:
    return ScoredChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title=title,
        chunk_index=0,
        content=content,
        page_number=page_number,
        score=0.03,
    )


def test_context_blocks_numbered_in_order_with_page_headers() -> None:
    chunks = [
        make_chunk("Doc A", "Alpha content.", 3),
        make_chunk("Doc B", "Beta content.", None),
    ]
    messages = build_messages("What is alpha?", chunks, [])
    prompt = messages[-1]["content"]
    assert "[1] (Doc A, p.3)\nAlpha content." in prompt
    assert "[2] (Doc B)\nBeta content." in prompt
    assert prompt.index("[1]") < prompt.index("[2]")
    assert prompt.rstrip().endswith("Question: What is alpha?")


def test_system_prompt_first_and_instructs_citations() -> None:
    messages = build_messages("q", [make_chunk("D", "c.", 1)], [])
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == SYSTEM_PROMPT
    assert "[n]" in SYSTEM_PROMPT
    assert "ONLY" in SYSTEM_PROMPT


def test_history_capped_at_six_most_recent() -> None:
    history: list[ChatMessage] = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i}"} for i in range(10)
    ]
    messages = build_messages("q", [], history)
    # system + capped history + final user prompt
    assert len(messages) == 1 + MAX_HISTORY_MESSAGES + 1
    assert messages[1]["content"] == "msg 4"  # oldest four dropped
    assert messages[-2]["content"] == "msg 9"


def test_no_chunks_yields_placeholder_context() -> None:
    messages = build_messages("anything?", [], [])
    prompt = messages[-1]["content"]
    assert "(no sources found)" in prompt
    assert "[1]" not in prompt

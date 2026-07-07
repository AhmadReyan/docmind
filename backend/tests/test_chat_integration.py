"""Integration: conversations CRUD and the SSE chat flow end to end."""

import pytest
from httpx import AsyncClient

from app.ingestion.worker import ingest_document
from tests.utils import parse_sse

pytestmark = pytest.mark.integration

DOC_TEXT = (
    "DocMind is a document intelligence platform for asking questions about your files. "
    "It retrieves relevant chunks using hybrid search. "
    "Answers always cite their sources with numbered markers."
)


async def _setup_user_with_document(client: AsyncClient, email: str) -> str:
    response = await client.post(
        "/api/auth/register", json={"email": email, "password": "password123"}
    )
    assert response.status_code == 201
    upload = await client.post(
        "/api/documents", files={"file": ("about.txt", DOC_TEXT.encode(), "text/plain")}
    )
    assert upload.status_code == 202
    doc_id: str = upload.json()["id"]
    await ingest_document({}, doc_id)
    return doc_id


async def test_conversation_crud(client: AsyncClient) -> None:
    await client.post(
        "/api/auth/register", json={"email": "crud@example.com", "password": "password123"}
    )
    created = await client.post("/api/conversations", json={})
    assert created.status_code == 201
    convo = created.json()
    assert convo["title"] == "New conversation"

    listing = await client.get("/api/conversations")
    assert listing.status_code == 200
    assert listing.json()["total"] == 1

    detail = await client.get(f"/api/conversations/{convo['id']}")
    assert detail.status_code == 200
    assert detail.json()["messages"] == []

    deleted = await client.delete(f"/api/conversations/{convo['id']}")
    assert deleted.status_code == 204
    assert (await client.get(f"/api/conversations/{convo['id']}")).status_code == 404


async def test_chat_sse_flow(client: AsyncClient) -> None:
    doc_id = await _setup_user_with_document(client, "chat@example.com")
    convo = (await client.post("/api/conversations", json={})).json()

    question = "What is DocMind and how does it cite sources?"
    response = await client.post(
        f"/api/conversations/{convo['id']}/messages", json={"content": question}
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"

    events = parse_sse(response.text)
    names = [name for name, _data in events]
    assert names[0] == "sources"
    assert names[-1] == "done"
    assert names.count("sources") == 1
    assert names.count("done") == 1
    assert "error" not in names
    token_events = [data for name, data in events if name == "token"]
    assert len(token_events) >= 1
    assert set(names[1:-1]) == {"token"}  # nothing between sources and done but tokens

    sources = events[0][1]["sources"]
    assert len(sources) >= 1
    assert sources[0]["index"] == 1
    assert sources[0]["document_id"] == doc_id
    assert sources[0]["document_title"] == "about"
    assert sources[0]["snippet"]
    assert sources[0]["score"] > 0

    done = events[-1][1]
    assert done["conversation_title"] == question[:60]

    streamed = "".join(data["delta"] for data in token_events)
    assert streamed.startswith("Based on your documents")

    # Assistant message persisted with content and frozen sources.
    detail = (await client.get(f"/api/conversations/{convo['id']}")).json()
    assert detail["title"] == question[:60]
    messages = detail["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[0]["content"] == question
    assert messages[0]["sources"] is None
    assert messages[1]["id"] == done["message_id"]
    assert messages[1]["content"] == streamed
    assert messages[1]["sources"] == sources


async def test_chat_with_no_documents_still_completes(client: AsyncClient) -> None:
    await client.post(
        "/api/auth/register", json={"email": "empty@example.com", "password": "password123"}
    )
    convo = (await client.post("/api/conversations", json={})).json()
    response = await client.post(
        f"/api/conversations/{convo['id']}/messages", json={"content": "Hello?"}
    )
    events = parse_sse(response.text)
    names = [name for name, _ in events]
    assert names[0] == "sources"
    assert events[0][1]["sources"] == []
    assert names[-1] == "done"
    streamed = "".join(d["delta"] for n, d in events if n == "token")
    assert "couldn't find relevant information" in streamed


async def test_chat_rate_limit_returns_plain_429(client: AsyncClient) -> None:
    await _setup_user_with_document(client, "limited@example.com")
    convo = (await client.post("/api/conversations", json={})).json()
    limit = 20  # settings.chat_rate_limit_per_minute
    status_codes = []
    for _ in range(limit + 1):
        response = await client.post(
            f"/api/conversations/{convo['id']}/messages", json={"content": "hi there"}
        )
        status_codes.append(response.status_code)
    assert status_codes[-1] == 429
    last = await client.post(
        f"/api/conversations/{convo['id']}/messages", json={"content": "hi again"}
    )
    assert last.status_code == 429
    assert last.headers["content-type"].startswith("application/json")
    assert last.json()["code"] == "rate_limited"


async def test_message_to_missing_conversation_is_404(client: AsyncClient) -> None:
    await client.post(
        "/api/auth/register", json={"email": "lost@example.com", "password": "password123"}
    )
    response = await client.post(
        "/api/conversations/00000000-0000-0000-0000-000000000000/messages",
        json={"content": "hello"},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"

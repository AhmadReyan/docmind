"""Integration: users can never see or touch each other's data (404, no leak)."""

from collections.abc import Callable

import pytest
from httpx import AsyncClient

from app.ingestion.worker import ingest_document

pytestmark = pytest.mark.integration


async def _register(client: AsyncClient, email: str) -> None:
    response = await client.post(
        "/api/auth/register", json={"email": email, "password": "password123"}
    )
    assert response.status_code == 201


async def test_user_b_cannot_access_user_a_document(
    client: AsyncClient, client_factory: Callable[[], AsyncClient]
) -> None:
    await _register(client, "usera@example.com")
    upload = await client.post(
        "/api/documents",
        files={"file": ("private.txt", b"User A private notes. Secret plans.", "text/plain")},
    )
    doc_id = upload.json()["id"]
    await ingest_document({}, doc_id)

    client_b = client_factory()
    await _register(client_b, "userb@example.com")

    for method, path in [
        ("GET", f"/api/documents/{doc_id}"),
        ("GET", f"/api/documents/{doc_id}/chunks"),
        ("DELETE", f"/api/documents/{doc_id}"),
    ]:
        response = await client_b.request(method, path)
        assert response.status_code == 404, (method, path)
        assert response.json() == {"detail": "Document not found", "code": "not_found"}

    # Document untouched for user A.
    assert (await client.get(f"/api/documents/{doc_id}")).status_code == 200
    # And B's listing is empty while A's is not.
    assert (await client_b.get("/api/documents")).json()["total"] == 0
    assert (await client.get("/api/documents")).json()["total"] == 1


async def test_user_b_cannot_access_user_a_conversation(
    client: AsyncClient, client_factory: Callable[[], AsyncClient]
) -> None:
    await _register(client, "convoa@example.com")
    convo_id = (await client.post("/api/conversations", json={})).json()["id"]

    client_b = client_factory()
    await _register(client_b, "convob@example.com")

    assert (await client_b.get(f"/api/conversations/{convo_id}")).status_code == 404
    assert (await client_b.delete(f"/api/conversations/{convo_id}")).status_code == 404
    posted = await client_b.post(
        f"/api/conversations/{convo_id}/messages", json={"content": "sneaky"}
    )
    assert posted.status_code == 404

    assert (await client.get(f"/api/conversations/{convo_id}")).status_code == 200


async def test_retrieval_only_searches_own_chunks(
    client: AsyncClient, client_factory: Callable[[], AsyncClient]
) -> None:
    await _register(client, "owner@example.com")
    upload = await client.post(
        "/api/documents",
        files={
            "file": (
                "zebra.txt",
                b"Zebra migration patterns are documented extensively here.",
                "text/plain",
            )
        },
    )
    await ingest_document({}, upload.json()["id"])

    client_b = client_factory()
    await _register(client_b, "searcher@example.com")
    convo = (await client_b.post("/api/conversations", json={})).json()
    response = await client_b.post(
        f"/api/conversations/{convo['id']}/messages",
        json={"content": "Tell me about zebra migration patterns"},
    )
    from tests.utils import parse_sse

    events = parse_sse(response.text)
    assert events[0][0] == "sources"
    assert events[0][1]["sources"] == []  # user A's chunks are invisible to B

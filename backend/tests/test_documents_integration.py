"""Integration: upload -> inline ingest -> chunks -> delete cascade."""

from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.config import get_settings
from app.db import get_session_factory
from app.ingestion.worker import ingest_document
from app.models import Chunk
from tests.utils import build_pdf

pytestmark = pytest.mark.integration

DOC_TEXT = (
    "DocMind is a document intelligence platform. It uses hybrid retrieval that "
    "combines vector search with keyword search. Results from both retrievers are "
    "fused using reciprocal rank fusion.\n\n"
    "Uploaded documents are split into overlapping chunks. Each chunk is embedded "
    "and stored in Postgres with pgvector."
)


async def _register(client: AsyncClient, email: str) -> None:
    response = await client.post(
        "/api/auth/register", json={"email": email, "password": "password123"}
    )
    assert response.status_code == 201


async def _upload_text(client: AsyncClient, name: str, text: str) -> dict:
    response = await client.post(
        "/api/documents", files={"file": (name, text.encode(), "text/plain")}
    )
    assert response.status_code == 202, response.text
    return response.json()


async def test_upload_ingest_chunks_delete(client: AsyncClient) -> None:
    await _register(client, "docs@example.com")
    doc = await _upload_text(client, "notes.txt", DOC_TEXT)
    assert doc["status"] == "pending"
    assert doc["title"] == "notes"
    assert doc["mime_type"] == "text/plain"

    # Run the ingestion task inline (no worker process).
    await ingest_document({}, doc["id"])

    detail = await client.get(f"/api/documents/{doc['id']}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["status"] == "ready"
    assert body["error_message"] is None
    assert body["page_count"] == 1
    assert body["chunk_count"] >= 1

    chunks = await client.get(f"/api/documents/{doc['id']}/chunks")
    assert chunks.status_code == 200
    chunk_page = chunks.json()
    assert chunk_page["total"] == body["chunk_count"]
    indexes = [c["chunk_index"] for c in chunk_page["items"]]
    assert indexes == sorted(indexes)
    assert all(c["content"].strip() for c in chunk_page["items"])
    assert all(c["token_count"] > 0 for c in chunk_page["items"])

    # Embeddings are stored on every chunk.
    async with get_session_factory()() as session:
        missing = await session.scalar(
            select(func.count()).select_from(Chunk).where(Chunk.embedding.is_(None))
        )
        assert missing == 0

    # File exists on disk under the contract path scheme.
    upload_root = Path(get_settings().upload_dir)
    stored = list(upload_root.rglob(f"{doc['id']}.txt"))
    assert len(stored) == 1

    deleted = await client.delete(f"/api/documents/{doc['id']}")
    assert deleted.status_code == 204
    assert (await client.get(f"/api/documents/{doc['id']}")).status_code == 404
    assert not list(upload_root.rglob(f"{doc['id']}.txt"))
    async with get_session_factory()() as session:
        remaining = await session.scalar(select(func.count()).select_from(Chunk))
        assert remaining == 0


async def test_pdf_upload_and_page_numbers(client: AsyncClient) -> None:
    await _register(client, "pdf@example.com")
    pdf = build_pdf(["Facts about apples on page one", "Facts about pears on page two"])
    response = await client.post(
        "/api/documents", files={"file": ("fruit.pdf", pdf, "application/pdf")}
    )
    assert response.status_code == 202
    doc = response.json()
    await ingest_document({}, doc["id"])

    detail = (await client.get(f"/api/documents/{doc['id']}")).json()
    assert detail["status"] == "ready"
    assert detail["page_count"] == 2
    chunks = (await client.get(f"/api/documents/{doc['id']}/chunks")).json()
    assert {c["page_number"] for c in chunks["items"]} == {1, 2}


async def test_corrupt_pdf_marks_document_failed(client: AsyncClient) -> None:
    await _register(client, "broken@example.com")
    response = await client.post(
        "/api/documents",
        files={"file": ("bad.pdf", b"this is not a pdf at all", "application/pdf")},
    )
    assert response.status_code == 202
    doc = response.json()
    await ingest_document({}, doc["id"])
    detail = (await client.get(f"/api/documents/{doc['id']}")).json()
    assert detail["status"] == "failed"
    assert detail["error_message"]


async def test_unsupported_type_and_mismatched_content_type(client: AsyncClient) -> None:
    await _register(client, "types@example.com")
    bad_ext = await client.post(
        "/api/documents", files={"file": ("evil.exe", b"MZ", "application/octet-stream")}
    )
    assert bad_ext.status_code == 415
    assert bad_ext.json()["code"] == "unsupported_file_type"

    mismatched = await client.post(
        "/api/documents", files={"file": ("notes.txt", b"hello", "application/pdf")}
    )
    assert mismatched.status_code == 415
    assert mismatched.json()["code"] == "unsupported_file_type"


async def test_oversized_file_rejected(client: AsyncClient) -> None:
    await _register(client, "big@example.com")
    too_big = b"a" * (get_settings().max_upload_bytes + 1)
    response = await client.post(
        "/api/documents", files={"file": ("big.txt", too_big, "text/plain")}
    )
    assert response.status_code == 413
    assert response.json()["code"] == "file_too_large"


async def test_listing_newest_first_with_pagination(client: AsyncClient) -> None:
    await _register(client, "lister@example.com")
    ids = []
    for i in range(3):
        doc = await _upload_text(client, f"doc-{i}.txt", f"Document number {i}. Some text.")
        ids.append(doc["id"])

    listing = await client.get("/api/documents", params={"limit": 2, "offset": 0})
    assert listing.status_code == 200
    page = listing.json()
    assert page["total"] == 3
    assert len(page["items"]) == 2
    assert page["items"][0]["id"] == ids[2]  # newest first

    rest = (await client.get("/api/documents", params={"limit": 2, "offset": 2})).json()
    assert len(rest["items"]) == 1
    assert rest["items"][0]["id"] == ids[0]

    over_limit = await client.get("/api/documents", params={"limit": 101})
    assert over_limit.status_code == 422
    assert over_limit.json()["code"] == "validation_error"

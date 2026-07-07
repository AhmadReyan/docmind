"""Integration: full auth flow against the real app + postgres."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


async def test_register_me_logout_flow(client: AsyncClient) -> None:
    response = await client.post(
        "/api/auth/register",
        json={"email": "Alice@Example.com", "password": "password123"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "alice@example.com"  # normalized to lowercase
    assert "docmind_token" in response.cookies

    me = await client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["id"] == body["id"]

    logout = await client.post("/api/auth/logout")
    assert logout.status_code == 204

    me_after = await client.get("/api/auth/me")
    assert me_after.status_code == 401
    assert me_after.json()["code"] == "unauthorized"


async def test_duplicate_email_conflict(client: AsyncClient) -> None:
    payload = {"email": "bob@example.com", "password": "password123"}
    first = await client.post("/api/auth/register", json=payload)
    assert first.status_code == 201
    dupe = await client.post(
        "/api/auth/register", json={"email": "BOB@example.com", "password": "otherpass99"}
    )
    assert dupe.status_code == 409
    assert dupe.json() == {"detail": "Email is already registered", "code": "email_taken"}


async def test_login_flows(client: AsyncClient) -> None:
    await client.post(
        "/api/auth/register", json={"email": "carol@example.com", "password": "password123"}
    )
    await client.post("/api/auth/logout")

    bad = await client.post(
        "/api/auth/login", json={"email": "carol@example.com", "password": "wrongpass1"}
    )
    assert bad.status_code == 401
    assert bad.json()["code"] == "invalid_credentials"

    missing = await client.post(
        "/api/auth/login", json={"email": "nobody@example.com", "password": "password123"}
    )
    assert missing.status_code == 401
    assert missing.json()["code"] == "invalid_credentials"

    good = await client.post(
        "/api/auth/login", json={"email": "CAROL@example.com", "password": "password123"}
    )
    assert good.status_code == 200
    assert (await client.get("/api/auth/me")).status_code == 200


async def test_validation_error_shape(client: AsyncClient) -> None:
    response = await client.post(
        "/api/auth/register", json={"email": "not-an-email", "password": "short"}
    )
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    assert isinstance(body["detail"], str)


async def test_protected_endpoints_require_auth(client: AsyncClient) -> None:
    for method, path in [
        ("GET", "/api/documents"),
        ("GET", "/api/conversations"),
        ("POST", "/api/auth/logout"),
    ]:
        response = await client.request(method, path)
        assert response.status_code == 401, path
        assert response.json()["code"] == "unauthorized"


async def test_health_is_public(client: AsyncClient) -> None:
    response = await client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["db"] is True
    assert body["redis"] is True
    assert body["providers"] == {"llm": "local", "embedding": "hash"}

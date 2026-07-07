"""Test configuration.

Unit tests need no containers. Integration tests (marked ``integration``) spin up
session-scoped pgvector and redis testcontainers and run the real ASGI app through
httpx. Tests always use the hash embedding provider and local LLM provider so no
model download or API key is ever required.
"""

import asyncio
import os
import subprocess
import tempfile
from collections.abc import AsyncIterator, Callable, Iterator

# Force fast, offline providers BEFORE any app import (conftest imports first).
os.environ["EMBEDDING_PROVIDER"] = "hash"
os.environ["LLM_PROVIDER"] = "local"
os.environ["JWT_SECRET"] = "integration-test-secret-at-least-32-bytes"
os.environ["COOKIE_SECURE"] = "false"
os.environ.setdefault("UPLOAD_DIR", tempfile.mkdtemp(prefix="docmind-tests-"))

import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

import app.db as app_db
from app.config import get_settings
from app.models import Base

get_settings.cache_clear()


def _docker_available() -> bool:
    try:
        result = subprocess.run(["docker", "info"], capture_output=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


@pytest.fixture(scope="session")
def docker() -> None:
    if not _docker_available():
        pytest.skip("Docker is not available; skipping integration tests")


async def _create_schema(url: str) -> None:
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()


@pytest.fixture(scope="session")
def pg_url(docker: None) -> Iterator[str]:
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("pgvector/pgvector:pg16", driver="asyncpg") as container:
        url = container.get_connection_url()
        asyncio.run(_create_schema(url))
        yield url


@pytest.fixture(scope="session")
def redis_url(docker: None) -> Iterator[str]:
    from testcontainers.redis import RedisContainer

    with RedisContainer("redis:7-alpine") as container:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(6379)
        yield f"redis://{host}:{port}/0"


@pytest.fixture
async def app(
    pg_url: str, redis_url: str, tmp_path_factory: pytest.TempPathFactory
) -> AsyncIterator[FastAPI]:
    """Fresh app per test wired to the containers; tables truncated on teardown."""
    os.environ["DATABASE_URL"] = pg_url
    os.environ["REDIS_URL"] = redis_url
    os.environ["UPLOAD_DIR"] = str(tmp_path_factory.mktemp("uploads"))
    get_settings.cache_clear()
    app_db._engine = None
    app_db._session_factory = None

    from app.main import create_app

    application = create_app()
    async with LifespanManager(application):
        yield application

    engine = app_db.get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text("TRUNCATE TABLE messages, conversations, chunks, documents, users CASCADE")
        )
    await engine.dispose()
    app_db._engine = None
    app_db._session_factory = None
    get_settings.cache_clear()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client


@pytest.fixture
async def client_factory(app: FastAPI) -> AsyncIterator[Callable[[], AsyncClient]]:
    """Create additional clients (separate cookie jars) against the same app."""
    clients: list[AsyncClient] = []

    def make() -> AsyncClient:
        http_client = AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")
        clients.append(http_client)
        return http_client

    yield make
    for http_client in clients:
        await http_client.aclose()

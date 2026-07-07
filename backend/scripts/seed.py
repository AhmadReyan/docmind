"""Idempotent demo seeder. Run with ``python -m scripts.seed``.

Creates the demo user (demo@docmind.dev / demo1234) if missing, then registers and
enqueues ingestion for every file in ``backend/seed_data/`` that the demo user does
not already have (matched by filename). Missing/empty seed_data is skipped gracefully.
"""

import asyncio
import uuid
from pathlib import Path, PurePosixPath

from arq import create_pool
from arq.connections import RedisSettings
from sqlalchemy import select

from app.config import get_settings
from app.core.security import hash_password
from app.db import get_engine, get_session_factory
from app.models import Document, User
from app.storage import build_storage_path, get_storage

DEMO_EMAIL = "demo@docmind.dev"
DEMO_PASSWORD = "demo1234"
INGEST_JOB_NAME = "ingest_document"

SEED_DATA_DIR = Path(__file__).resolve().parent.parent / "seed_data"

_EXTENSION_MIME = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".md": "text/markdown",
}


async def main() -> None:
    settings = get_settings()
    session_factory = get_session_factory()
    created_user = False
    enqueued: list[str] = []
    skipped: list[str] = []

    async with session_factory() as session:
        user = await session.scalar(select(User).where(User.email == DEMO_EMAIL))
        if user is None:
            user = User(email=DEMO_EMAIL, password_hash=hash_password(DEMO_PASSWORD))
            session.add(user)
            await session.commit()
            await session.refresh(user)
            created_user = True

        seed_files = (
            sorted(p for p in SEED_DATA_DIR.iterdir() if p.is_file())
            if SEED_DATA_DIR.is_dir()
            else []
        )
        pool = None
        try:
            for path in seed_files:
                ext = path.suffix.lower()
                mime_type = _EXTENSION_MIME.get(ext)
                if mime_type is None:
                    skipped.append(f"{path.name} (unsupported type)")
                    continue
                existing = await session.scalar(
                    select(Document).where(
                        Document.user_id == user.id, Document.filename == path.name
                    )
                )
                if existing is not None:
                    skipped.append(f"{path.name} (already seeded)")
                    continue

                data = path.read_bytes()
                document_id = uuid.uuid4()
                storage_path = build_storage_path(user.id, document_id, ext)
                get_storage(settings).save(storage_path, data)
                document = Document(
                    id=document_id,
                    user_id=user.id,
                    title=PurePosixPath(path.name).stem,
                    filename=path.name,
                    mime_type=mime_type,
                    size_bytes=len(data),
                    storage_path=storage_path,
                    status="pending",
                )
                session.add(document)
                await session.commit()

                if pool is None:
                    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
                await pool.enqueue_job(INGEST_JOB_NAME, str(document_id))
                enqueued.append(path.name)
        finally:
            if pool is not None:
                await pool.aclose()

    await get_engine().dispose()

    print(f"Demo user {DEMO_EMAIL}: {'created' if created_user else 'already exists'}")
    if not SEED_DATA_DIR.is_dir():
        print(f"Seed data directory {SEED_DATA_DIR} not found; no documents seeded.")
    print(f"Documents enqueued for ingestion: {len(enqueued)}")
    for name in enqueued:
        print(f"  + {name}")
    if skipped:
        print(f"Skipped: {len(skipped)}")
        for entry in skipped:
            print(f"  - {entry}")


if __name__ == "__main__":
    asyncio.run(main())

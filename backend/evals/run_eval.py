"""DocMind retrieval evaluation harness.

Runs the golden question set (evals/golden_set.json) against the real
retrieval pipeline and reports hit_rate@k and MRR. Used locally and as a CI
quality gate (--min-hit-rate).

Usage (from backend/):

    python -m evals.run_eval [--top-k 5] [--min-hit-rate 0.8] [--summary out.md]

Infrastructure:
- If EVAL_DATABASE_URL is set, that database is used as-is (it must be a
  pgvector-enabled Postgres; the harness runs `alembic upgrade head` on it).
- Otherwise a disposable pgvector/pgvector:pg16 container is started via
  testcontainers (requires Docker) and torn down afterwards.

Providers:
- Embeddings come from `get_embedding_provider(Settings())`, so the
  EMBEDDING_PROVIDER env var selects the provider. Defaults to `local`
  (fastembed) so the eval runs without any API keys.

Metrics per case:
- hit@k  — 1 if any of the top-k retrieved chunks belongs to the expected
  document AND contains at least one answer keyword (case-insensitive,
  whitespace-normalized), else 0.
- rank   — 1-based position of the first such chunk (None on a miss).
- MRR    — mean over cases of 1/rank (0 for misses).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
SEED_DIR = BACKEND_DIR / "seed_data"
GOLDEN_SET_PATH = Path(__file__).resolve().parent / "golden_set.json"

SEED_FILES: dict[str, str] = {
    "aurora-employee-handbook.md": "text/markdown",
    "atlas-product-spec.md": "text/markdown",
    "solaris-research-notes.txt": "text/plain",
}

_WS = re.compile(r"\s+")


def _norm(text: str) -> str:
    """Lowercase and collapse whitespace so keywords match across line wraps."""
    return _WS.sub(" ", text.lower()).strip()


@dataclass
class CaseResult:
    case_id: str
    question: str
    expected_document: str
    hit: bool
    rank: int | None
    top_document: str | None


# --------------------------------------------------------------------------
# Database bootstrap
# --------------------------------------------------------------------------


def _to_asyncpg_url(url: str) -> str:
    return re.sub(r"^postgresql(\+\w+)?://", "postgresql+asyncpg://", url)


def _start_database() -> tuple[str, Any]:
    """Return (asyncpg URL, container-or-None). Honors EVAL_DATABASE_URL."""
    external = os.environ.get("EVAL_DATABASE_URL")
    if external:
        print("Using external database from EVAL_DATABASE_URL")
        return _to_asyncpg_url(external), None

    from testcontainers.postgres import PostgresContainer

    print("Starting disposable pgvector/pgvector:pg16 container ...")
    container = PostgresContainer("pgvector/pgvector:pg16")
    container.start()
    url = _to_asyncpg_url(container.get_connection_url())
    return url, container


def _run_migrations(database_url: str) -> None:
    """Run `alembic upgrade head` in a subprocess (alembic/env.py reads DATABASE_URL)."""
    print("Applying migrations (alembic upgrade head) ...")
    env = {**os.environ, "DATABASE_URL": database_url}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        raise SystemExit("alembic upgrade head failed")


# --------------------------------------------------------------------------
# Ingestion (calls the app's own extract/chunk/embed building blocks)
# --------------------------------------------------------------------------
def _extract_and_chunk(path: Path, mime_type: str) -> list[dict[str, Any]]:
    """Run the app's real ingestion pipeline: extract_pages -> chunk_pages."""
    from app.ingestion.chunking import chunk_pages
    from app.ingestion.extract import extract_pages

    pages = extract_pages(path.read_bytes(), mime_type)
    return [
        {"content": c.content, "token_count": c.token_count, "page_number": c.page_number}
        for c in chunk_pages(pages)
    ]


async def _ingest_seed_docs(
    session: Any, user_id: uuid.UUID, provider: Any
) -> dict[str, uuid.UUID]:
    """Insert the seed documents + embedded chunks. Returns filename -> document_id."""
    from app.models import Chunk, Document

    doc_ids: dict[str, uuid.UUID] = {}
    for filename, mime_type in SEED_FILES.items():
        path = SEED_DIR / filename
        chunks = _extract_and_chunk(path, mime_type)
        embeddings = await provider.embed([c["content"] for c in chunks])

        document = Document(
            user_id=user_id,
            title=path.stem,
            filename=filename,
            mime_type=mime_type,
            size_bytes=path.stat().st_size,
            storage_path=str(path),
            status="ready",
            chunk_count=len(chunks),
        )
        session.add(document)
        await session.flush()

        for index, (chunk, embedding) in enumerate(zip(chunks, embeddings, strict=True)):
            session.add(
                Chunk(
                    document_id=document.id,
                    user_id=user_id,
                    chunk_index=index,
                    content=chunk["content"],
                    page_number=chunk["page_number"],
                    token_count=chunk["token_count"],
                    embedding=embedding,
                )
            )
        await session.commit()
        doc_ids[filename] = document.id
        print(f"  ingested {filename}: {len(chunks)} chunks")
    return doc_ids


# --------------------------------------------------------------------------
# Evaluation
# --------------------------------------------------------------------------


def _score_case(
    case: dict[str, Any],
    results: list[Any],  # list[ScoredChunk]
    doc_ids: dict[str, uuid.UUID],
) -> CaseResult:
    expected_id = doc_ids[case["expected_document"]]
    keywords = [_norm(k) for k in case["answer_keywords"]]

    rank: int | None = None
    for position, scored in enumerate(results, start=1):
        if scored.document_id != expected_id:
            continue
        content = _norm(scored.content)
        if any(keyword in content for keyword in keywords):
            rank = position
            break

    return CaseResult(
        case_id=case["id"],
        question=case["question"],
        expected_document=case["expected_document"],
        hit=rank is not None,
        rank=rank,
        top_document=results[0].document_title if results else None,
    )


async def _run(
    args: argparse.Namespace, database_url: str
) -> tuple[list[CaseResult], float, float]:
    # Imported here so env vars (DATABASE_URL, EMBEDDING_PROVIDER) are already set.
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.config import Settings
    from app.models import User
    from app.providers.base import get_embedding_provider
    from app.rag.retrieval import retrieve

    settings = Settings()
    provider = get_embedding_provider(settings)
    print(f"Embedding provider: {provider.name} (dim={provider.dimension})")

    cases = json.loads(GOLDEN_SET_PATH.read_text(encoding="utf-8"))
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with sessions() as session:
            user = User(
                email=f"eval-{uuid.uuid4().hex[:8]}@docmind.dev",
                password_hash="!eval-user-no-login",
            )
            session.add(user)
            await session.commit()

            print("Ingesting seed documents ...")
            doc_ids = await _ingest_seed_docs(session, user.id, provider)

            print(f"Running {len(cases)} golden cases (top_k={args.top_k}) ...")
            results: list[CaseResult] = []
            for case in cases:
                scored = await retrieve(
                    session,
                    user.id,
                    case["question"],
                    embedding_provider=provider,
                    top_k=args.top_k,
                )
                results.append(_score_case(case, scored, doc_ids))
    finally:
        await engine.dispose()

    hit_rate = sum(r.hit for r in results) / len(results) if results else 0.0
    mrr = sum(1.0 / r.rank for r in results if r.rank) / len(results) if results else 0.0
    return results, hit_rate, mrr


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------


def _print_report(results: list[CaseResult], hit_rate: float, mrr: float, top_k: int) -> None:
    id_width = max(len(r.case_id) for r in results)
    print()
    print(f"{'case':<{id_width}}  {'hit':<4} {'rank':<5} expected document")
    print(f"{'-' * id_width}  {'-' * 4} {'-' * 5} {'-' * 30}")
    for r in results:
        hit = "yes" if r.hit else "NO"
        rank = str(r.rank) if r.rank else "-"
        print(f"{r.case_id:<{id_width}}  {hit:<4} {rank:<5} {r.expected_document}")
    print()
    print(f"hit_rate@{top_k}: {hit_rate:.3f}   MRR: {mrr:.3f}   cases: {len(results)}")


def _write_summary(
    path: str, results: list[CaseResult], hit_rate: float, mrr: float, top_k: int
) -> None:
    lines = [
        "## RAG retrieval eval",
        "",
        f"**hit_rate@{top_k}: {hit_rate:.3f}** · **MRR: {mrr:.3f}** · {len(results)} cases",
        "",
        "| Case | Question | Hit | Rank |",
        "|---|---|---|---|",
    ]
    for r in results:
        question = r.question if len(r.question) <= 70 else r.question[:67] + "..."
        lines.append(
            f"| `{r.case_id}` | {question} | {'✅' if r.hit else '❌'} | {r.rank or '—'} |"
        )
    lines.append("")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"Wrote markdown summary to {path}")


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m evals.run_eval",
        description="Evaluate DocMind retrieval against the golden question set.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="number of chunks to retrieve per question (default: 5)",
    )
    parser.add_argument(
        "--min-hit-rate",
        type=float,
        default=0.0,
        help="exit 1 if hit_rate@k falls below this threshold (default: 0.0)",
    )
    parser.add_argument(
        "--summary",
        type=str,
        default=None,
        help="path to append a markdown results table (e.g. $GITHUB_STEP_SUMMARY)",
    )
    args = parser.parse_args()

    # Zero-key default; must be set before any app.* import constructs Settings.
    os.environ.setdefault("EMBEDDING_PROVIDER", "local")

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    started = time.monotonic()
    database_url, container = _start_database()
    os.environ["DATABASE_URL"] = database_url
    try:
        _run_migrations(database_url)
        results, hit_rate, mrr = asyncio.run(_run(args, database_url))
    finally:
        if container is not None:
            container.stop()

    _print_report(results, hit_rate, mrr, args.top_k)
    if args.summary:
        _write_summary(args.summary, results, hit_rate, mrr, args.top_k)
    print(f"Done in {time.monotonic() - started:.1f}s")

    if hit_rate < args.min_hit_rate:
        print(
            f"FAIL: hit_rate@{args.top_k} {hit_rate:.3f} < required {args.min_hit_rate:.3f}",
            file=sys.stderr,
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()

"""Health endpoint: database + redis reachability and configured provider names."""

import logging

from fastapi import APIRouter, Request
from sqlalchemy import text

from app.api.deps import SessionDep, SettingsDep
from app.schemas.chat import HealthOut, ProvidersOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthOut)
async def health(request: Request, session: SessionDep, settings: SettingsDep) -> HealthOut:
    db_ok = False
    try:
        await session.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        logger.exception("Health check: database unreachable")

    redis_ok = False
    pool = getattr(request.app.state, "arq_pool", None)
    if pool is not None:
        try:
            redis_ok = bool(await pool.ping())
        except Exception:
            logger.exception("Health check: redis unreachable")

    return HealthOut(
        status="ok",
        db=db_ok,
        redis=redis_ok,
        # Provider registry names match the settings keys by construction.
        providers=ProvidersOut(llm=settings.llm_provider, embedding=settings.embedding_provider),
    )

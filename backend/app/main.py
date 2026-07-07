"""DocMind FastAPI application factory.

Every non-2xx response body is ``{"detail": str, "code": str}`` per
docs/api-contract.md, enforced by the global exception handlers below.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import auth, chat, documents, health
from app.config import get_settings
from app.core.errors import ApiError

logger = logging.getLogger(__name__)

# Fallback codes for HTTPExceptions raised without an explicit ApiError code
# (e.g. Starlette's 404 for unknown routes or 405 for wrong methods).
_DEFAULT_ERROR_CODES = {
    400: "validation_error",
    401: "unauthorized",
    404: "not_found",
    405: "validation_error",
    409: "email_taken",
    413: "file_too_large",
    415: "unsupported_file_type",
    422: "validation_error",
    429: "rate_limited",
}


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    app.state.arq_pool = pool
    try:
        yield
    finally:
        await pool.aclose()


async def _http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code = (
        exc.code
        if isinstance(exc, ApiError)
        else _DEFAULT_ERROR_CODES.get(exc.status_code, "internal_error")
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": str(exc.detail), "code": code},
        headers=exc.headers,
    )


async def _validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    detail = "; ".join(
        f"{'.'.join(str(loc) for loc in error.get('loc', []))}: {error.get('msg', 'invalid')}"
        for error in exc.errors()
    )
    return JSONResponse(
        status_code=422,
        content={"detail": detail or "Validation error", "code": "validation_error"},
    )


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "code": "internal_error"},
    )


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="DocMind API",
        version="1.0.0",
        lifespan=_lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(documents.router)
    app.include_router(chat.router)
    return app


app = create_app()

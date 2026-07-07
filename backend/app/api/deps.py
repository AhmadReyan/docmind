"""Shared FastAPI dependencies: current user, pagination, settings, ARQ pool."""

from dataclasses import dataclass
from typing import Annotated, cast

import jwt
from arq.connections import ArqRedis
from fastapi import Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.core.errors import ApiError
from app.core.security import COOKIE_NAME, decode_token
from app.db import get_session
from app.models import User

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def _unauthorized(detail: str) -> ApiError:
    return ApiError(status.HTTP_401_UNAUTHORIZED, detail, "unauthorized")


async def get_current_user(request: Request, session: SessionDep, settings: SettingsDep) -> User:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise _unauthorized("Not authenticated")
    try:
        user_id = decode_token(token, settings)
    except jwt.InvalidTokenError as exc:
        raise _unauthorized("Invalid or expired token") from exc
    user = await session.get(User, user_id)
    if user is None:
        raise _unauthorized("User no longer exists")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


@dataclass(frozen=True)
class Pagination:
    limit: int
    offset: int


def pagination_params(
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Pagination:
    return Pagination(limit=limit, offset=offset)


PaginationDep = Annotated[Pagination, Depends(pagination_params)]


def get_arq_pool(request: Request) -> ArqRedis:
    """ARQ redis pool created in the app lifespan (also used for rate limiting)."""
    return cast(ArqRedis, request.app.state.arq_pool)


ArqPoolDep = Annotated[ArqRedis, Depends(get_arq_pool)]

"""Password hashing (Argon2 via pwdlib), JWT issue/verify, and auth-cookie helpers."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from fastapi import Response
from pwdlib import PasswordHash

from app.config import Settings

COOKIE_NAME = "docmind_token"

_password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _password_hasher.verify(password, password_hash)


def create_access_token(
    user_id: uuid.UUID,
    settings: Settings,
    *,
    expires_delta: timedelta | None = None,
) -> str:
    """Encode a JWT whose ``sub`` is the user id; expiry defaults to settings.jwt_expires_hours."""
    delta = (
        expires_delta if expires_delta is not None else timedelta(hours=settings.jwt_expires_hours)
    )
    now = datetime.now(UTC)
    payload: dict[str, Any] = {"sub": str(user_id), "iat": now, "exp": now + delta}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str, settings: Settings) -> uuid.UUID:
    """Return the user id from a token, raising ``jwt.InvalidTokenError`` on any problem.

    Expired tokens raise ``jwt.ExpiredSignatureError`` (a subclass of InvalidTokenError).
    """
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    try:
        return uuid.UUID(str(payload.get("sub")))
    except ValueError as exc:
        raise jwt.InvalidTokenError("Invalid subject claim") from exc


def set_auth_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=settings.jwt_expires_hours * 3600,
        path="/",
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
    )


def clear_auth_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
    )

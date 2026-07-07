"""Unit tests for password hashing and JWT round-trips."""

import uuid
from datetime import timedelta

import jwt
import pytest

from app.config import Settings
from app.core.security import (
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)


@pytest.fixture
def settings() -> Settings:
    return Settings(jwt_secret="unit-test-secret-with-at-least-32-bytes!", jwt_expires_hours=1)


def test_password_hash_and_verify_roundtrip() -> None:
    hashed = hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert hashed.startswith("$argon2")
    assert verify_password("correct horse battery staple", hashed)
    assert not verify_password("wrong password", hashed)


def test_jwt_encode_decode_roundtrip(settings: Settings) -> None:
    user_id = uuid.uuid4()
    token = create_access_token(user_id, settings)
    assert decode_token(token, settings) == user_id


def test_expired_jwt_rejected(settings: Settings) -> None:
    token = create_access_token(uuid.uuid4(), settings, expires_delta=timedelta(seconds=-10))
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_token(token, settings)


def test_jwt_wrong_secret_rejected(settings: Settings) -> None:
    token = create_access_token(uuid.uuid4(), settings)
    other = Settings(jwt_secret="a-different-secret-also-32-bytes-long!!!")
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(token, other)


def test_jwt_garbage_subject_rejected(settings: Settings) -> None:
    bad = jwt.encode({"sub": "not-a-uuid"}, settings.jwt_secret, algorithm="HS256")
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(bad, settings)

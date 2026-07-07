"""Auth endpoints: register, login, logout, me. JWT lives in an httpOnly cookie."""

from fastapi import APIRouter, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, SessionDep, SettingsDep
from app.core.errors import ApiError
from app.core.security import (
    clear_auth_cookie,
    create_access_token,
    hash_password,
    set_auth_cookie,
    verify_password,
)
from app.models import User
from app.schemas.auth import LoginRequest, RegisterRequest, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
) -> User:
    email = payload.email.lower()
    existing = await session.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise ApiError(status.HTTP_409_CONFLICT, "Email is already registered", "email_taken")
    user = User(email=email, password_hash=hash_password(payload.password))
    session.add(user)
    try:
        await session.commit()
    except IntegrityError as exc:  # concurrent registration race
        raise ApiError(
            status.HTTP_409_CONFLICT, "Email is already registered", "email_taken"
        ) from exc
    await session.refresh(user)
    set_auth_cookie(response, create_access_token(user.id, settings), settings)
    return user


@router.post("/login", response_model=UserOut)
async def login(
    payload: LoginRequest,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
) -> User:
    email = payload.email.lower()
    user = await session.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise ApiError(
            status.HTTP_401_UNAUTHORIZED, "Invalid email or password", "invalid_credentials"
        )
    set_auth_cookie(response, create_access_token(user.id, settings), settings)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(user: CurrentUser, response: Response, settings: SettingsDep) -> None:
    del user  # auth required per contract; the user object itself is not needed
    clear_auth_cookie(response, settings)


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> User:
    return user

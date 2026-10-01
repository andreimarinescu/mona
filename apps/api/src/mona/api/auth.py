"""C2 §2.5 auth endpoints."""

from typing import Annotated, Literal

import anyio.to_thread
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import APIRouter, Request, Response
from pydantic import Field
from sqlalchemy import select, update

from mona import clock
from mona.api.deps import Engine, SessionDep
from mona.api.errors import ApiFailure, errors
from mona.api.guard import cookie_token, request_scheme
from mona.api.session import (
    COOKIE,
    SESSION_DAYS,
    TooManyAttempts,
    create_session,
    csrf_token,
    is_locked,
    live_session,
    revoke,
    throttle,
)
from mona.db.models import AuthSession, Profile
from mona.dto.base import Dto

router = APIRouter(prefix="/api/auth", tags=["auth"])
hasher = PasswordHasher()
MIN_PASSWORD = 8


class AuthState(Dto):
    authenticated: bool
    locked: bool
    locale: Literal["en", "fr", "ro"]
    csrf_token: str | None
    auto_lock_minutes: int | None
    profile_name: str | None


class UnlockRequest(Dto):
    password: Annotated[str, Field(min_length=1, max_length=1024)]


class PasswordChange(Dto):
    current_password: Annotated[str, Field(min_length=1, max_length=1024)]
    new_password: Annotated[str, Field(min_length=1, max_length=1024)]


def verify_password(stored: str, password: str) -> bool:
    try:
        return hasher.verify(stored, password)
    except (VerificationError, InvalidHashError):
        return False


def _secure(request: Request) -> bool:
    headers = {k.lower(): v for k, v in request.scope.get("headers") or []}
    host = headers.get(b"host", b"").decode("latin-1").split(":")[0]
    return request_scheme(request.scope, headers) == "https" or host == "localhost"


def _set_cookie(response: Response, request: Request, token: str) -> None:
    response.set_cookie(
        COOKIE,
        token,
        max_age=SESSION_DAYS * 86400,
        path="/",
        httponly=True,
        samesite="strict",
        secure=_secure(request),
    )


async def _state(engine, token: str | None) -> AuthState:  # noqa: ANN001
    async with engine.connect() as conn:
        profile = (
            await conn.execute(select(Profile.locale, Profile.auto_lock_minutes, Profile.name))
        ).first()
        session = await live_session(conn, token)
    locale = profile.locale if profile else "en"
    if session is None or profile is None:
        return AuthState(
            authenticated=False, locked=False, locale=locale, csrf_token=None,
            auto_lock_minutes=None, profile_name=None,
        )  # fmt: skip
    return AuthState(
        authenticated=True,
        locked=session.locked,
        locale=locale,
        csrf_token=csrf_token(token or ""),
        auto_lock_minutes=profile.auto_lock_minutes,
        profile_name=None if session.locked else profile.name,
    )


@router.get("/state", operation_id="getAuthState", responses=errors(503))
async def state(request: Request, engine: Engine) -> AuthState:
    headers = {k.lower(): v for k, v in request.scope.get("headers") or []}
    token = None if headers.get(b"authorization") else cookie_token(headers)
    return await _state(engine, token)


@router.post("/unlock", operation_id="unlock", responses=errors(400, 401, 403, 415, 429))
async def unlock(
    body: UnlockRequest, request: Request, response: Response, engine: Engine
) -> AuthState:
    async with engine.connect() as conn:
        stored = (await conn.execute(select(Profile.password_hash))).scalar()
    if stored is None:
        raise ApiFailure(401, "invalid_password", "Wrong password.")

    async def verify() -> bool:
        return await anyio.to_thread.run_sync(verify_password, stored, body.password)

    try:
        ok = await throttle.attempt(verify)
    except TooManyAttempts as e:
        raise ApiFailure(
            429, "too_many_attempts", "Too many attempts.",
            headers={"Retry-After": str(e.retry_after)},
        ) from None  # fmt: skip
    if not ok:
        raise ApiFailure(401, "invalid_password", "Wrong password.")
    if hasher.check_needs_rehash(stored):
        new_hash = await anyio.to_thread.run_sync(hasher.hash, body.password)
        async with engine.begin() as conn:
            await conn.execute(update(Profile).values(password_hash=new_hash))
    headers = {k.lower(): v for k, v in request.scope.get("headers") or []}
    token = None if headers.get(b"authorization") else cookie_token(headers)
    now = clock.now()
    async with engine.begin() as conn:
        session = await live_session(conn, token)
        if session is None:
            _, token = await create_session(conn, request.headers.get("user-agent"))
            _set_cookie(response, request, token)
        else:
            await conn.execute(
                update(AuthSession)
                .where(AuthSession.id == session.id)
                .values(last_active_at=now, updated_at=now)
            )
        await conn.execute(update(Profile).values(locked_at=None, updated_at=now))
    return await _state(engine, token)


@router.post("/lock", operation_id="lock", status_code=204, responses=errors(401, 403))
async def lock(engine: Engine, _: SessionDep) -> Response:
    now = clock.now()
    async with engine.begin() as conn:
        await conn.execute(update(Profile).values(locked_at=now, updated_at=now))
    return Response(status_code=204)


@router.post("/heartbeat", operation_id="heartbeat", status_code=204, responses=errors(401, 423))
async def heartbeat(_: SessionDep) -> Response:
    return Response(status_code=204)


@router.post("/logout", operation_id="logout", status_code=204, responses=errors(401, 403))
async def logout(request: Request, engine: Engine, session: SessionDep) -> Response:
    async with engine.begin() as conn:
        await revoke(conn, only=session.id)
    response = Response(status_code=204)
    response.delete_cookie(
        COOKIE, path="/", httponly=True, samesite="strict", secure=_secure(request)
    )
    return response


@router.put(
    "/password", operation_id="changePassword", status_code=204,
    responses=errors(400, 401, 403, 422, 423),
)  # fmt: skip
async def change_password(body: PasswordChange, engine: Engine, session: SessionDep) -> Response:
    async with engine.connect() as conn:
        stored = (await conn.execute(select(Profile.password_hash))).scalar_one()
    if not await anyio.to_thread.run_sync(verify_password, stored, body.current_password):
        raise ApiFailure(401, "invalid_password", "Wrong password.", field="currentPassword")
    if len(body.new_password) < MIN_PASSWORD:
        raise ApiFailure(
            422, "invalid_value", "The new password is too short.", field="newPassword"
        )
    new_hash = await anyio.to_thread.run_sync(hasher.hash, body.new_password)
    now = clock.now()
    async with engine.begin() as conn:
        await conn.execute(
            update(Profile).values(password_hash=new_hash, password_changed_at=now, updated_at=now)
        )
        await revoke(conn, but=session.id)
    return Response(status_code=204)


__all__ = ["router", "is_locked"]

"""Shared route plumbing: the services context, the session, the request locale, ids, lists."""

import base64
import binascii
import hashlib
import json
from collections.abc import Callable
from functools import lru_cache
from typing import Annotated, Any

import anyio.to_thread
from fastapi import Depends, Path, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from mona import clock
from mona.api.errors import ApiFailure
from mona.api.session import Session
from mona.db import get_engine, get_sync_engine
from mona.db.models import Profile
from mona.dto.base import Dto
from mona.fileops.errors import FileOpError
from mona.ids import is_id
from mona.services import Ctx, make_context
from mona.settings import get_settings

Engine = Annotated[AsyncEngine, Depends(get_engine)]


def _now():  # noqa: ANN202
    return clock.now()


@lru_cache
def get_ctx() -> Ctx:
    from mona.api.cardnotes import commit_hook

    ctx = make_context(get_sync_engine(), get_settings().mona_data_dir, clock=_now)
    ctx.ops.on_commit = commit_hook(ctx.ops.on_commit)
    return ctx


CtxDep = Annotated[Ctx, Depends(get_ctx)]


async def run[R](fn: Callable[..., R], *args: Any, **kwargs: Any) -> R:
    """A sync service call off the event loop; service errors become C2 errors."""
    from mona.api.errors import from_service

    try:
        return await anyio.to_thread.run_sync(lambda: fn(*args, **kwargs))
    except FileOpError as err:
        raise from_service(err) from None


def current_session(request: Request) -> Session:
    session = request.scope.get("state", {}).get("session")
    if session is None:
        raise ApiFailure(401, "unauthenticated", "No live session.")
    return session


SessionDep = Annotated[Session, Depends(current_session)]


async def request_lang(engine: Engine) -> str:
    """C2 §1.1 item 5: `profile.locale` at the time of the request."""
    async with engine.connect() as conn:
        return (await conn.execute(select(Profile.locale))).scalar() or "en"


Lang = Annotated[str, Depends(request_lang)]


def path_id(prefix: str, name: str) -> Any:
    """A path id; the wrong prefix is the same 404 as an unknown id (C2 §1.1 item 3)."""

    def check(value: Annotated[str, Path(alias=name)]) -> str:
        if not is_id(value, prefix):
            raise ApiFailure(404, "not_found", "Not found.")
        return value

    return Annotated[str, Depends(check)]


def body_id(value: str | None, prefix: str, field: str) -> str | None:
    if value is not None and not is_id(value, prefix):
        raise ApiFailure(400, "invalid_request", f"Expected a {prefix}_ id.", field=field)
    return value


# --- lists (C2 §1.3) ---

Offset = Annotated[int, Query(ge=0)]
PageLimit = Annotated[int, Query(ge=1, le=200)]
FeedLimit = Annotated[int, Query(ge=1, le=100)]


class Page[T](Dto):
    items: list[T]
    total: int
    offset: int
    limit: int


class Feed[T](Dto):
    items: list[T]
    next_cursor: str | None


def _digest(params: dict[str, Any]) -> str:
    raw = json.dumps(params, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def encode_cursor(key: list[Any], params: dict[str, Any]) -> str:
    raw = json.dumps({"k": key, "h": _digest(params)}, separators=(",", ":"), default=str)
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(cursor: str | None, params: dict[str, Any]) -> list[Any] | None:
    """The sort key of the last item returned; a cursor from other filters is 400."""
    if cursor is None:
        return None
    bad = ApiFailure(400, "invalid_request", "The cursor belongs to another query.", field="cursor")
    try:
        data = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
        key, digest = data["k"], data["h"]
    except (ValueError, KeyError, TypeError, binascii.Error):
        raise bad from None
    if digest != _digest(params) or not isinstance(key, list):
        raise bad
    return key


class Empty(BaseModel):
    pass


def polled(request: Request, model: type[BaseModel], body: Any) -> Response:
    """C2 §1.5: the JSON body with a weak ETag; 304 when `If-None-Match` names it."""
    raw = json.dumps(
        model.model_validate(body).model_dump(mode="json", by_alias=True),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
    tag = f'W/"{hashlib.sha256(raw).hexdigest()[:32]}"'
    given = request.headers.get("if-none-match", "")
    if tag in (t.strip() for t in given.split(",")):
        return Response(status_code=304, headers={"ETag": tag})
    return Response(raw, media_type="application/json", headers={"ETag": tag})

"""An HTTP client for the api with a live browser session (cookie + CSRF header)."""

from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any

import httpx
import psycopg

from mona import clock
from mona.api.session import COOKIE, csrf_token, new_token, token_hash
from mona.ids import new_id
from mona.settings import get_settings


def new_session(*, last_active=None, expires_in=timedelta(days=30)) -> tuple[str, str]:  # noqa: ANN001
    """Inserts a live session row; returns (session id, cookie token)."""
    token, sid, now = new_token(), new_id("ses"), clock.now()
    with psycopg.connect(get_settings().libpq_url) as conn:
        conn.execute(
            "INSERT INTO auth_sessions (id, token_hash, created_at, expires_at, last_active_at)"
            " VALUES (%s, %s, %s, %s, %s)",
            (sid, token_hash(token), now, now + expires_in, last_active or now),
        )
    return sid, token


def session_headers(token: str) -> dict[str, str]:
    return {"x-csrf-token": csrf_token(token)}


@asynccontextmanager
async def api_client(target: Any, *, token: str | None = None, **kw: Any):
    """`target` is an app or an ASGI transport; a fresh session unless `token` is given."""
    transport = target if isinstance(target, httpx.ASGITransport) else httpx.ASGITransport(target)
    if token is None:
        _, token = new_session()
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://t",
        cookies={COOKIE: token},
        headers=session_headers(token),
        **kw,
    ) as c:
        yield c

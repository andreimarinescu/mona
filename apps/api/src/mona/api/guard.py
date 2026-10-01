"""C2 §2.7 enforcement, before any body byte is read: session, lock, CSRF and Origin, media type,
then the size limit. Plus the request log line (C9 §7) and the 500/503 envelope."""

import logging
import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy.exc import DBAPIError, OperationalError
from starlette.requests import cookie_parser
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from mona.api.errors import envelope
from mona.api.session import COOKIE, Session, csrf_ok, live_session, touch
from mona.db import get_engine
from mona.http import refuse
from mona.logs import exc_summary
from mona.settings import get_settings

logger = logging.getLogger("mona.request")

KIB = 1024
MIB = 1024 * KIB
DEFAULT_LIMIT = 64 * KIB
CHAT_LIMIT = 32 * KIB
INTAKE_LIMIT = 250 * MIB
READS = frozenset({"GET", "HEAD"})

OPEN = frozenset({("GET", "/api/health"), ("HEAD", "/api/health"), ("GET", "/api/auth/state")})
UNLOCK = ("POST", "/api/auth/unlock")
LOCK_EXEMPT = frozenset({("POST", "/api/auth/lock"), ("POST", "/api/auth/logout")})
NOT_JSON = ("/api/intake",)


@dataclass(frozen=True)
class Limit:
    max_bytes: int
    status: int
    body: dict[str, Any]


TOO_LARGE = envelope("too_large", "The request body is too large.")
CHAT_INVALID = envelope("invalid_request", "The request is invalid.")


def limit_for(path: str) -> Limit:
    if path == "/api/chat":
        return Limit(CHAT_LIMIT, 400, CHAT_INVALID)
    if path == "/api/intake" or path.startswith("/api/intake/"):
        return Limit(INTAKE_LIMIT, 413, TOO_LARGE)
    return Limit(DEFAULT_LIMIT, 413, TOO_LARGE)


def _headers(scope: Scope) -> dict[bytes, bytes]:
    return {k.lower(): v for k, v in scope.get("headers") or []}


def cookie_token(headers: dict[bytes, bytes]) -> str | None:
    raw = headers.get(b"cookie")
    if not raw:
        return None
    return cookie_parser(raw.decode("latin-1")).get(COOKIE) or None


def trusted_proxy(scope: Scope) -> bool:
    client = scope.get("client")
    proxies = get_settings().proxies
    return bool(client and client[0] in proxies)


def request_scheme(scope: Scope, headers: dict[bytes, bytes]) -> str:
    forwarded = headers.get(b"x-forwarded-proto")
    if forwarded and trusted_proxy(scope):
        return forwarded.decode("latin-1").split(",")[0].strip().lower()
    return scope.get("scheme", "http")


def app_origin(scope: Scope, headers: dict[bytes, bytes]) -> str:
    configured = get_settings().mona_public_origin
    if configured:
        return configured.rstrip("/")
    host = headers.get(b"host", b"").decode("latin-1")
    return f"{request_scheme(scope, headers)}://{host}"


def origin_ok(scope: Scope, headers: dict[bytes, bytes]) -> bool:
    origin = headers.get(b"origin")
    return origin is None or origin.decode("latin-1") == app_origin(scope, headers)


def has_body(headers: dict[bytes, bytes]) -> bool:
    length = headers.get(b"content-length")
    if length is not None:
        return length.strip() not in (b"", b"0")
    return b"chunked" in headers.get(b"transfer-encoding", b"").lower()


def is_json(headers: dict[bytes, bytes]) -> bool:
    ctype = headers.get(b"content-type", b"").split(b";")[0].strip().lower()
    return ctype == b"application/json"


class ApiGuard:
    """Pure ASGI: nothing here reads the body; the size limit wraps `receive`."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "") if scope["type"] == "http" else ""
        if not (path == "/api" or path.startswith("/api/")):
            await self.app(scope, receive, send)
            return
        headers = _headers(scope)
        method = scope["method"]
        refusal, session = await self._check(scope, headers, method, path)
        if refusal is not None:
            status, body, extra = refusal
            await refuse(send, status, body, extra)
            return
        scope.setdefault("state", {})["session"] = session
        limit = limit_for(path)
        declared = headers.get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > limit.max_bytes:
            await refuse(send, limit.status, limit.body)
            return
        received = 0
        started = refused = False
        write = method not in READS and session is not None

        async def counted() -> Message:
            nonlocal received, refused, started
            if refused:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit.max_bytes:
                    refused = True
                    if not started:
                        started = True
                        await refuse(send, limit.status, limit.body)
                    return {"type": "http.disconnect"}
            return message

        async def tracked(message: Message) -> None:
            nonlocal started
            if refused:
                return
            if message["type"] == "http.response.start":
                started = True
                if write and 200 <= message["status"] < 300:
                    async with get_engine().begin() as conn:
                        await touch(conn, session.id)  # type: ignore[union-attr]
            await send(message)

        try:
            await self.app(scope, counted, tracked)
        except Exception:
            if not refused:
                raise

    async def _check(
        self, scope: Scope, headers: dict[bytes, bytes], method: str, path: str
    ) -> tuple[tuple[int, dict[str, Any], dict[str, str] | None] | None, Session | None]:
        key = (method, path)
        if key in OPEN:
            return None, None
        if key == UNLOCK:
            if not origin_ok(scope, headers):
                return (403, envelope("csrf_failed", "Foreign origin."), None), None
            return None, None
        token = None if headers.get(b"authorization") else cookie_token(headers)
        async with get_engine().connect() as conn:
            session = await live_session(conn, token)
        if session is None:
            return (401, envelope("unauthenticated", "No live session."), None), None
        if session.locked and key not in LOCK_EXEMPT:
            return (423, envelope("locked", "The session is locked."), None), session
        if method not in READS:
            given = headers.get(b"x-csrf-token")
            token_ok = given is not None and csrf_ok(session.token, given.decode("latin-1"))
            if not token_ok or not origin_ok(scope, headers):
                return (403, envelope("csrf_failed", "Missing or invalid CSRF token."), None), None
            if has_body(headers) and not is_json(headers) and not path.startswith(NOT_JSON):
                body = envelope("unsupported_media_type", "Send application/json.")
                return (415, body, None), None
        return None, session


class RequestLog:
    """C9 §7: one line per request with the route template, status and duration; unexpected
    exceptions become the 500 (or 503) envelope and are logged by class and constraint."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        t0 = time.monotonic()
        status = 0

        async def tracked(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, tracked)
        except Exception as exc:
            logger.error("%s %s failed: %s", scope["method"], _template(scope), exc_summary(exc))
            if status == 0:
                if _unavailable(exc):
                    status = 503
                    await refuse(send, 503, envelope("unavailable", "The database is down."))
                else:
                    status = 500
                    await refuse(send, 500, envelope("internal", "Something went wrong."))
        finally:
            ms = round((time.monotonic() - t0) * 1000)
            logger.info("%s %s %s %dms", scope["method"], _template(scope), status, ms)


def _template(scope: Scope) -> str:
    route = scope.get("route")
    return getattr(route, "path", None) or ("/mcp" if scope.get("path", "") == "/mcp" else "-")


def _unavailable(exc: BaseException) -> bool:
    if isinstance(exc, OperationalError | ConnectionRefusedError):
        return True
    return isinstance(exc, DBAPIError) and exc.connection_invalidated

"""Pure ASGI guards: request body caps per path prefix."""

import json
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class BodyLimit:
    """Refuses bodies over the limit of the first matching path prefix, before the app runs.

    `limits` maps a path prefix to (max bytes, status, JSON body of the refusal). A capped
    request's body is read up front and replayed to the app.
    """

    def __init__(self, app: ASGIApp, limits: dict[str, tuple[int, int, dict[str, Any]]]) -> None:
        self.app = app
        self.limits = limits

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        limit = self._limit_for(scope)
        if limit is None:
            await self.app(scope, receive, send)
            return
        max_bytes, status, body = limit
        declared = dict(scope.get("headers") or []).get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > max_bytes:
            await refuse(send, status, body)
            return
        chunks: list[bytes] = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunks.append(message.get("body", b""))
            size += len(chunks[-1])
            if size > max_bytes:
                await refuse(send, status, body)
                return
            if not message.get("more_body", False):
                break
        replayed = False

        async def replay() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)

    def _limit_for(self, scope: Scope) -> tuple[int, int, dict[str, Any]] | None:
        if scope["type"] != "http":
            return None
        path = scope.get("path", "")
        for prefix, limit in self.limits.items():
            if path == prefix or path.startswith(prefix + "/"):
                return limit
        return None


async def refuse(
    send: Send, status: int, body: dict[str, Any], headers: dict[str, str] | None = None
) -> None:
    raw = json.dumps(body).encode()
    extra = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", b"%d" % len(raw)),
                *extra,
            ],
        }
    )
    await send({"type": "http.response.body", "body": raw})

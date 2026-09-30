"""A stand-in for the Hermes API server, and helpers to drive `POST /api/chat` against it."""

import json
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from mona.app import create_app
from mona.chat.hermes import HermesClient, get_hermes

BODY = {
    "message": "What am I looking at?",
    "pageContext": {"route": "/documents/doc_x", "summary": "Document viewer"},
    "locale": "en",
}


def chunk(delta: dict | None = None, finish: str | None = None, **extra: Any) -> str:
    body = {"choices": [{"index": 0, "delta": delta or {}, "finish_reason": finish}], **extra}
    return "data: " + json.dumps(body)


def tool_event(name: str, call_id: str, status: str) -> list[str]:
    return [
        "event: hermes.tool.progress",
        "data: "
        + json.dumps({"tool": f"mcp__mona__{name}", "toolCallId": call_id, "status": status}),
        "",
    ]


def sse_body(lines: list[str]) -> bytes:
    return ("\n".join(lines) + "\n").encode()


def tool_message(*refs: str) -> dict:
    wrapped = json.dumps({"result": json.dumps({"card_refs": list(refs)})})
    return {
        "role": "tool",
        "content": f'<untrusted_tool_result source="x">\n{wrapped}\n</untrusted>',
    }


class FakeHermes:
    """`stream` is the completions body; `during_stream` runs first, as the MCP tools would."""

    def __init__(
        self,
        stream: bytes | Callable[[], Awaitable[bytes]] = b"",
        *,
        during_stream: Callable[[], Awaitable[Any]] | None = None,
        messages: list | Callable[[], list] | None = None,
        down: set[str] = frozenset(),
        session_status: int = 201,
        on_session: Callable[[dict], None] | None = None,
    ) -> None:
        self.stream = stream
        self.during_stream = during_stream
        self.messages = messages
        self.down = set(down)
        self.session_status = session_status
        self.on_session = on_session
        self.requests: list[httpx.Request] = []

    def paths(self) -> list[str]:
        return [r.url.path for r in self.requests]

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if any(path.startswith(d) for d in self.down):
            raise httpx.ConnectError("down", request=request)
        if path == "/api/sessions":
            body = json.loads(request.content)
            if self.on_session:
                self.on_session(body)
            if self.session_status == 409:
                err = {"error": {"code": "session_exists", "message": "exists"}}
                return httpx.Response(409, json=err)
            return httpx.Response(self.session_status, json={"session": {"id": body["id"]}})
        if path == "/v1/chat/completions":
            if self.during_stream:
                await self.during_stream()
            content = self.stream if isinstance(self.stream, bytes) else await self.stream()
            return httpx.Response(
                200, content=content, headers={"content-type": "text/event-stream"}
            )
        if path.endswith("/messages"):
            data = self.messages() if callable(self.messages) else self.messages or []
            return httpx.Response(200, json={"object": "list", "data": data})
        return httpx.Response(404)

    def client(self) -> HermesClient:
        return HermesClient("http://hermes", "key", transport=httpx.MockTransport(self))


def app_with(fake: FakeHermes):
    app = create_app()
    app.dependency_overrides[get_hermes] = fake.client
    return app


async def post_chat(fake: FakeHermes, body: dict | None = None, **overrides: Any):
    body = {**BODY, **(body or {}), **overrides}
    transport = httpx.ASGITransport(app=app_with(fake))
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        res = await c.post("/api/chat", json=body)
    return res, parse(res.text) if res.status_code == 200 else None


def parse(text: str) -> list:
    out = []
    for frame in text.split("\n\n"):
        if frame.startswith("data: "):
            body = frame[6:]
            out.append(body if body == "[DONE]" else json.loads(body))
    return out


def types(chunks: list) -> list[str]:
    return [c if c == "[DONE]" else c["type"] for c in chunks]


def meta(chunks: list) -> dict:
    return chunks[0]["messageMetadata"]

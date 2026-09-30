"""Calls Mona's MCP tools over HTTP through the real `/mcp` route (auth and channel included)."""

import json
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import httpx

from mona.app import create_app
from tests.conftest import SERVICE_KEY


@dataclass
class ToolResult:
    status: int
    is_error: bool
    data: dict[str, Any]
    text: str


def rpc_result(res: httpx.Response) -> dict[str, Any]:
    return _rpc_body(res)["result"]


def _rpc_body(res: httpx.Response) -> dict[str, Any]:
    if res.headers.get("content-type", "").startswith("text/event-stream"):
        for line in res.text.splitlines():
            if line.startswith("data:"):
                return json.loads(line[5:])
        raise AssertionError(f"no data line in {res.text!r}")
    return res.json()


@asynccontextmanager
async def mcp_client():
    app = create_app()
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://api:8765") as c:
            yield c


async def rpc(
    client: httpx.AsyncClient,
    method: str,
    params: dict | None = None,
    *,
    channel: str | None = "web",
    auth: str | None = f"Bearer {SERVICE_KEY}",
) -> httpx.Response:
    headers = {"accept": "application/json, text/event-stream"}
    if auth is not None:
        headers["authorization"] = auth
    if channel is not None:
        headers["x-mona-channel"] = channel
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    return await client.post("/mcp", json=body, headers=headers)


async def call(tool: str, args: dict | None = None, **kw: Any) -> ToolResult:
    async with mcp_client() as c:
        res = await rpc(c, "tools/call", {"name": tool, "arguments": args or {}}, **kw)
    if res.status_code != 200:
        return ToolResult(res.status_code, True, {}, res.text)
    result = _rpc_body(res)["result"]
    text = result["content"][0]["text"] if result.get("content") else ""
    if result.get("isError"):
        return ToolResult(200, True, json.loads(text), text)
    return ToolResult(200, False, result.get("structuredContent") or json.loads(text), text)


async def list_tools(**kw: Any) -> list[dict[str, Any]]:
    async with mcp_client() as c:
        res = await rpc(c, "tools/list", **kw)
    return _rpc_body(res)["result"]["tools"]

"""Spike MCP server shaped like `docs/spikes/s1/spike_mcp.py`; each tool records its cards."""

import hmac
from datetime import UTC, datetime
from typing import Any

from fastmcp import FastMCP
from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import AsyncConnection
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from mona.db import get_engine
from mona.ids import new_id
from mona.settings import get_settings
from mona.spike import data
from mona.spike.tables import card_events, chat_turns, interviews

mcp = FastMCP("mona-spike")


async def _attributed_turn(conn: AsyncConnection, channel: str) -> str | None:
    """C3 §5.2: the single open, unexpired web turn, else none."""
    if channel != "web":
        return None
    rows = (
        await conn.execute(
            select(chat_turns.c.id)
            .where(chat_turns.c.status == "open", chat_turns.c.lease_expires_at > func.now())
            .limit(2)
        )
    ).all()
    return rows[0].id if len(rows) == 1 else None


async def record_cards(
    tool: str, cards: list[tuple[str, dict[str, str]]], channel: str = "web"
) -> list[str]:
    """Insert one `card_events` row per (kind, subject); returns the card refs."""
    if not cards:
        return []
    async with get_engine().begin() as conn:
        turn_id = await _attributed_turn(conn, channel)
        refs = [new_id("crd") for _ in cards]
        await conn.execute(
            insert(card_events),
            [
                {
                    "id": ref,
                    "tool": tool,
                    "kind": kind,
                    "subject": subject,
                    "channel": channel,
                    "turn_id": turn_id,
                }
                for ref, (kind, subject) in zip(refs, cards, strict=True)
            ],
        )
    return refs


@mcp.tool
async def search_documents(query: str, entity: str | None = None) -> dict[str, Any]:
    """Search the practice archive. Returns matching document ids with titles; use get_document
    for details."""
    ids = data.search(query, entity)
    refs = await record_cards("search_documents", [("doc", {"document_id": i}) for i in ids])
    return {
        "document_ids": ids,
        "results": [{"id": i, "title": data.DOCUMENTS[i]["title"]} for i in ids],
        "count": len(ids),
        "card_refs": refs,
    }


@mcp.tool
async def get_document(document_id: str) -> dict[str, Any]:
    """Fetch one document's fields (title, entity, amount in EUR, due date)."""
    doc = data.document_summary(document_id)
    if doc is None:
        return {"error": "not_found", "document_id": document_id}
    refs = await record_cards("get_document", [("doc", {"document_id": document_id})])
    return {
        "id": document_id,
        "title": doc["title"],
        "entity": doc["entityName"],
        "amount": doc["amount"]["value"],
        "due": doc["dueDate"],
        "card_refs": refs,
    }


@mcp.tool
async def start_interview(topic: str) -> dict[str, Any]:
    """Start a short interview with the user about how to file documents on a topic (e.g. a
    supplier). The question appears as a card in the chat; don't repeat it in your reply."""
    interview_id = new_id("int")
    created = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = data.interview_payload(interview_id, new_id("qst"), topic, created)
    async with get_engine().begin() as conn:
        await conn.execute(insert(interviews).values(id=interview_id, topic=topic, payload=payload))
    refs = await record_cards("start_interview", [("interview", {"interview_id": interview_id})])
    return {"interview_id": interview_id, "status": "ready", "questions": 1, "card_refs": refs}


class ServiceKeyAuth(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        key = get_settings().mona_service_key
        given = request.headers.get("authorization", "")
        expected = f"Bearer {key.get_secret_value()}" if key else ""
        if not key or not hmac.compare_digest(given.encode(), expected.encode()):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)


def build_mcp_app():
    return mcp.http_app(path="/mcp", middleware=[Middleware(ServiceKeyAuth)], stateless_http=True)

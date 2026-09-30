"""Card emission from `card_events` during a turn, and finish-time reconciliation (C3 §5)."""

import logging
import re
from collections.abc import Iterable
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from mona.spike import data
from mona.spike.tables import card_events, interviews

logger = logging.getLogger(__name__)

CARD_REF = re.compile(r"crd_[0-9a-hjkmnp-tv-z]{26}")

Chunk = dict[str, Any]


async def card_chunk(conn: AsyncConnection, kind: str, subject: dict[str, str]) -> Chunk | None:
    """The `data-<kind>` chunk for a card, from current state; None if the subject is gone."""
    if kind == "doc":
        doc = data.document_summary(subject["document_id"])
        return doc and {"type": "data-doc", "id": doc["id"], "data": doc}
    if kind == "interview":
        row = (
            await conn.execute(
                select(interviews.c.payload).where(interviews.c.id == subject["interview_id"])
            )
        ).first()
        return row and {
            "type": "data-interview",
            "id": subject["interview_id"],
            "data": row.payload,
        }
    return None


async def _emit_rows(conn: AsyncConnection, rows: Iterable[Any]) -> list[Chunk]:
    out = []
    for row in rows:
        chunk = await card_chunk(conn, row.kind, row.subject)
        if chunk is None:
            logger.warning("card %s: subject %s is gone", row.id, row.subject)
        else:
            out.append(chunk)
        await conn.execute(
            update(card_events).where(card_events.c.id == row.id).values(emitted_at=func.now())
        )
    return out


async def emit_pending(
    engine: AsyncEngine, turn_id: str, completed_tools: list[str]
) -> list[Chunk]:
    """Cards attributed to this turn by tools that have completed in it, not yet emitted."""
    if not completed_tools:
        return []
    async with engine.begin() as conn:
        rows = (
            await conn.execute(
                select(card_events)
                .where(
                    card_events.c.turn_id == turn_id,
                    card_events.c.emitted_at.is_(None),
                    card_events.c.tool.in_(set(completed_tools)),
                )
                .order_by(card_events.c.created_at)
            )
        ).all()
        return await _emit_rows(conn, rows)


def refs_in_tool_messages(messages: list[dict[str, Any]]) -> list[str]:
    refs: list[str] = []
    for m in messages:
        if m.get("role") == "tool":
            refs += [r for r in CARD_REF.findall(m.get("content") or "") if r not in refs]
    return refs


def messages_of_turn(messages: list[dict[str, Any]], user_ordinal: int) -> list[dict[str, Any]]:
    """The messages after the `user_ordinal`-th user message, up to the next user message."""
    seen, out = 0, []
    for m in messages:
        if m.get("role") == "user":
            seen += 1
            if seen > user_ordinal:
                break
            continue
        if seen == user_ordinal:
            out.append(m)
    return out


async def reconcile(engine: AsyncEngine, turn_id: str, refs: list[str]) -> list[Chunk]:
    """C3 §5.4 steps 4–5: emit this turn's cards found in its tool results; un-attribute strays."""
    async with engine.begin() as conn:
        found = {
            r.id: r
            for r in (
                await conn.execute(select(card_events).where(card_events.c.id.in_(refs)))
            ).all()
        }
        to_emit = []
        for ref in refs:
            row = found.get(ref)
            if row is None or (row.turn_id not in (None, turn_id)):
                continue
            if row.turn_id is None:
                await conn.execute(
                    update(card_events).where(card_events.c.id == ref).values(turn_id=turn_id)
                )
            if row.emitted_at is None:
                to_emit.append(row)
        await conn.execute(
            update(card_events)
            .where(
                card_events.c.turn_id == turn_id,
                card_events.c.emitted_at.is_(None),
                card_events.c.id.not_in(refs),
            )
            .values(turn_id=None)
        )
        return await _emit_rows(conn, to_emit)

"""Card emission from `card_events` during a turn, and finish-time reconciliation (C3 §5)."""

import logging
import re
from collections.abc import Iterable
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from mona.db.models import CardEvent
from mona.dto.load import SUBJECT_KEYS, card_payload

logger = logging.getLogger(__name__)

CARD_REF = re.compile(r"crd_[0-9a-hjkmnp-tv-z]{26}")

Chunk = dict[str, Any]


async def card_chunk(conn: AsyncConnection, kind: str, subject: dict[str, str]) -> Chunk | None:
    """The `data-<kind>` chunk for a card from current state; None if the subject is gone."""
    subject_id = subject.get(SUBJECT_KEYS.get(kind, ""))
    if subject_id is None:
        return None
    data = await card_payload(conn, kind, subject_id)
    return {"type": f"data-{kind}", "id": subject_id, "data": data} if data is not None else None


async def _emit_rows(conn: AsyncConnection, rows: Iterable[Any]) -> list[Chunk]:
    out = []
    for row in rows:
        chunk = await card_chunk(conn, row.kind, row.subject)
        if chunk is None:
            logger.warning("card %s: its %s subject is gone", row.id, row.kind)
        else:
            out.append(chunk)
        await conn.execute(
            update(CardEvent).where(CardEvent.id == row.id).values(emitted_at=func.now())
        )
    return out


async def emit_pending(
    engine: AsyncEngine, turn_id: str, completed_tools: Iterable[str]
) -> list[Chunk]:
    """C3 §5.3: this turn's unemitted cards whose tool has completed in it, oldest first."""
    tools = set(completed_tools)
    if not tools:
        return []
    async with engine.begin() as conn:
        rows = (
            await conn.execute(
                select(CardEvent)
                .where(
                    CardEvent.turn_id == turn_id,
                    CardEvent.emitted_at.is_(None),
                    CardEvent.tool.in_(tools),
                )
                .order_by(CardEvent.created_at, CardEvent.id)
                .with_for_update()
            )
        ).all()
        return await _emit_rows(conn, rows)


def messages_of_turn(messages: list[dict[str, Any]], user_text: str) -> list[dict[str, Any]] | None:
    """The messages after the last user message, if that message is this turn's; else None."""
    last = max((i for i, m in enumerate(messages) if m.get("role") == "user"), default=None)
    if last is None or (messages[last].get("content") or "").strip() != user_text:
        return None
    return messages[last + 1 :]


def refs_in_tool_messages(messages: list[dict[str, Any]]) -> list[str]:
    refs: list[str] = []
    for m in messages:
        if m.get("role") == "tool":
            refs += [r for r in CARD_REF.findall(m.get("content") or "") if r not in refs]
    return refs


async def reconcile(engine: AsyncEngine, turn_id: str, refs: list[str]) -> list[Chunk]:
    """C3 §5.4 steps 4–5: emit this turn's cards found in its tool results; un-attribute strays."""
    async with engine.begin() as conn:
        found = {
            r.id: r
            for r in (
                await conn.execute(
                    select(CardEvent).where(CardEvent.id.in_(refs)).with_for_update()
                )
            ).all()
        }
        to_emit = []
        for ref in refs:
            row = found.get(ref)
            if row is None:
                logger.warning("turn %s: card %s is not in card_events", turn_id, ref)
                continue
            if row.turn_id not in (None, turn_id):
                continue
            if row.turn_id is None:
                await conn.execute(
                    update(CardEvent).where(CardEvent.id == ref).values(turn_id=turn_id)
                )
            if row.emitted_at is None:
                to_emit.append(row)
        await conn.execute(
            update(CardEvent)
            .where(
                CardEvent.turn_id == turn_id,
                CardEvent.emitted_at.is_(None),
                CardEvent.id.not_in(refs),
            )
            .values(turn_id=None)
        )
        return await _emit_rows(conn, to_emit)

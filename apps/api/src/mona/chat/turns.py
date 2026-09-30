"""Conversation rows and the turn lease (C3 §4.1, §5.1, §7.1)."""

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from sqlalchemy import exists, func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from mona.chat import notes
from mona.chat.overlay import reply_language
from mona.db.models import ChatTurn, Conversation
from mona.ids import new_id, new_ulid

LEASE = timedelta(seconds=120)
TITLE_MAX = 60


class TurnInProgress(Exception):
    pass


@dataclass
class Turn:
    id: str
    conversation_id: str
    ui_message_id: str
    user_text: str
    reply_language: str
    language_pinned: bool
    needs_session: bool
    notes: list[str] = field(default_factory=list)


def title_for(message: str) -> str:
    """C3 §7.1: cut at the last word boundary before 60 characters, with "…" when cut."""
    if len(message) <= TITLE_MAX:
        return message
    head = message[: TITLE_MAX - 1]
    cut = head.rsplit(" ", 1)[0] if " " in head else head
    return cut.rstrip() + "…"


async def open_turn(
    engine: AsyncEngine,
    conversation_id: str | None,
    message: str,
    locale: str,
    requested_language: str | None,
) -> Turn:
    """One transaction: the conversation (if new), expired leases failed, the turn, the notes."""
    async with engine.begin() as conn:
        cid = conversation_id or new_id("cnv")
        if conversation_id is None:
            await conn.execute(insert(Conversation).values(id=cid, title=title_for(message)))
        await conn.execute(
            update(ChatTurn)
            .where(
                ChatTurn.conversation_id == cid,
                ChatTurn.status == "open",
                ChatTurn.lease_expires_at < func.now(),
            )
            .values(status="failed", error_code="lease_expired", closed_at=func.now())
        )
        previous = (
            await conn.execute(
                select(ChatTurn.reply_language)
                .where(ChatTurn.conversation_id == cid)
                .order_by(ChatTurn.opened_at.desc(), ChatTurn.id.desc())
                .limit(1)
            )
        ).scalar()
        language, pinned = reply_language(message, requested_language, previous, locale)
        needs_session = not (
            await conn.execute(
                select(exists().where(ChatTurn.conversation_id == cid, ChatTurn.status == "closed"))
            )
        ).scalar()
        turn = Turn(
            id=new_id("trn"),
            conversation_id=cid,
            ui_message_id=new_ulid(),
            user_text=message,
            reply_language=language,
            language_pinned=pinned,
            needs_session=needs_session,
        )
        try:
            await conn.execute(
                insert(ChatTurn).values(
                    id=turn.id,
                    conversation_id=cid,
                    user_text=message,
                    ui_message_id=turn.ui_message_id,
                    reply_language=language,
                    lease_expires_at=func.now() + LEASE,
                )
            )
        except IntegrityError as e:
            raise TurnInProgress from e
        turn.notes = await notes.consume(conn, cid, turn.id)
    return turn


async def touch(engine: AsyncEngine, turn: Turn) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            update(ChatTurn)
            .where(ChatTurn.id == turn.id, ChatTurn.status == "open")
            .values(lease_expires_at=func.now() + LEASE)
        )


async def close_turn(
    engine: AsyncEngine,
    turn: Turn,
    status: str,
    *,
    parts: list[dict[str, Any]],
    release_notes: bool = False,
    **values: Any,
) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            update(ChatTurn)
            .where(ChatTurn.id == turn.id)
            .values(status=status, closed_at=func.now(), parts=parts, **values)
        )
        await conn.execute(
            update(Conversation)
            .where(Conversation.id == turn.conversation_id)
            .values(last_message_at=func.now(), updated_at=func.now())
        )
        if release_notes:
            await notes.release(conn, turn.id)

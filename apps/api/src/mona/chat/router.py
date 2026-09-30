"""`POST /api/chat` (HermesEngine adapter) and transcript reload (C3)."""

import json
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated, Any, Literal

import anyio
import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from mona.chat import cards
from mona.chat.hermes import HermesClient, HermesError, get_hermes
from mona.chat.overlay import build_overlay, reply_language
from mona.chat.transcript import build_ui_messages
from mona.chat.translate import SSEParser, Translator
from mona.db import get_engine
from mona.ids import new_id
from mona.spike.tables import card_events, chat_turns, conversations

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

LEASE = timedelta(seconds=120)
LEASE_TOUCH_S = 10.0
STREAM_HEADERS = {
    "cache-control": "no-cache",
    "x-vercel-ai-ui-message-stream": "v1",
    "x-accel-buffering": "no",
}


class PageContext(BaseModel):
    route: str = Field(max_length=200)
    summary: str = Field(max_length=300)


class ChatRequest(BaseModel):
    conversationId: str | None = None
    message: str = Field(min_length=1, max_length=4000)
    pageContext: PageContext
    locale: Literal["en", "fr", "ro"]

    @field_validator("message")
    @classmethod
    def _trimmed(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("message is empty")
        return v


def sse(chunk: dict[str, Any] | str) -> str:
    body = chunk if isinstance(chunk, str) else json.dumps(chunk, ensure_ascii=False)
    return f"data: {body}\n\n"


def title_for(message: str) -> str:
    if len(message) < 60:
        return message
    cut = message[:59].rsplit(" ", 1)[0] or message[:59]
    return cut + "…"


def offline_stream(message_id: str, metadata: dict[str, Any]) -> list[str]:
    return [
        sse({"type": "start", "messageId": message_id, "messageMetadata": metadata}),
        sse({"type": "start-step"}),
        sse({"type": "error", "errorText": "mona_offline"}),
        sse({"type": "finish-step"}),
        sse({"type": "finish", "finishReason": "error"}),
        sse("[DONE]"),
    ]


@dataclass
class Turn:
    id: str
    conversation_id: str
    hermes_session_id: str
    ui_message_id: str
    user_ordinal: int
    reply_language: str


async def open_turn(engine: AsyncEngine, conv: Any, req: ChatRequest) -> Turn:
    """C3 §5.1: fail expired open turns, then insert this one; a live open turn → 409."""
    async with engine.begin() as conn:
        await conn.execute(
            update(chat_turns)
            .where(
                chat_turns.c.conversation_id == conv.id,
                chat_turns.c.status == "open",
                chat_turns.c.lease_expires_at < func.now(),
            )
            .values(status="failed", error_code="lease_expired", closed_at=func.now())
        )
        previous = (
            await conn.execute(
                select(chat_turns.c.reply_language)
                .where(chat_turns.c.conversation_id == conv.id)
                .order_by(chat_turns.c.opened_at.desc())
                .limit(1)
            )
        ).scalar()
        delivered = (
            await conn.execute(
                select(func.count())
                .select_from(chat_turns)
                .where(
                    chat_turns.c.conversation_id == conv.id,
                    func.coalesce(chat_turns.c.error_code, "").not_like("hermes\\_%"),
                )
            )
        ).scalar_one()
        turn = Turn(
            id=new_id("trn"),
            conversation_id=conv.id,
            hermes_session_id=conv.hermes_session_id,
            ui_message_id=new_id("msg"),
            user_ordinal=delivered + 1,
            reply_language=reply_language(req.message, previous, req.locale),
        )
        try:
            await conn.execute(
                insert(chat_turns).values(
                    id=turn.id,
                    conversation_id=conv.id,
                    user_ordinal=turn.user_ordinal,
                    ui_message_id=turn.ui_message_id,
                    reply_language=turn.reply_language,
                    lease_expires_at=func.now() + LEASE,
                )
            )
        except IntegrityError as e:
            raise HTTPException(409, {"code": "turn_in_progress"}) from e
    return turn


async def close_turn(engine: AsyncEngine, turn: Turn, status: str, **values: Any) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            update(chat_turns)
            .where(chat_turns.c.id == turn.id)
            .values(status=status, closed_at=func.now(), **values)
        )
        await conn.execute(
            update(conversations)
            .where(conversations.c.id == turn.conversation_id)
            .values(last_message_at=func.now())
        )


async def run_turn(
    engine: AsyncEngine, hermes: HermesClient, turn: Turn, req: ChatRequest
) -> AsyncIterator[str]:
    yield sse(
        {
            "type": "start",
            "messageId": turn.ui_message_id,
            "messageMetadata": {
                "conversationId": turn.conversation_id,
                "turnId": turn.id,
                "replyLanguage": turn.reply_language,
            },
        }
    )
    yield sse({"type": "start-step"})
    overlay = build_overlay(req.pageContext.route, req.pageContext.summary, turn.reply_language)
    upstream = [{"role": "system", "content": overlay}, {"role": "user", "content": req.message}]
    parser, tr = SSEParser(), Translator()
    status, error_code = "open", None
    last_touch = time.monotonic()
    try:
        try:
            async with hermes.stream_completion(turn.hermes_session_id, upstream) as lines:
                async for line in lines:
                    ev = parser.feed(line)
                    if ev is None:
                        continue
                    if time.monotonic() - last_touch > LEASE_TOUCH_S:
                        last_touch = time.monotonic()
                        await _touch(engine, turn)
                    if ev.comment:
                        yield ": keepalive\n\n"
                        continue
                    for chunk in tr.feed(ev):
                        yield sse(chunk)
                        if chunk["type"] == "tool-output-available":
                            for card in await cards.emit_pending(
                                engine, turn.id, tr.completed_tools
                            ):
                                yield sse(card)
                    if tr.done:
                        break
        except HermesError as e:
            logger.warning("turn %s: Hermes unreachable: %s", turn.id, e.code)
            status, error_code = "failed", e.code
            yield sse({"type": "error", "errorText": "mona_offline"})
            yield sse({"type": "finish-step"})
            yield sse({"type": "finish", "finishReason": "error"})
            yield sse("[DONE]")
            return
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("turn %s: upstream broke: %r", turn.id, e)

        for chunk in tr.close():
            yield sse(chunk)
        for card in await cards.emit_pending(engine, turn.id, tr.completed_tools):
            yield sse(card)
        for card in await _reconcile(engine, hermes, turn):
            yield sse(card)
        if not tr.done:
            status, error_code = "failed", "stream_interrupted"
            yield sse({"type": "error", "errorText": "stream_interrupted"})
            yield sse({"type": "finish", "finishReason": "error"})
        else:
            status = "closed"
            yield sse({"type": "finish-step"})
            yield sse(
                {
                    "type": "finish",
                    "finishReason": tr.ui_finish_reason,
                    "messageMetadata": {"reasoningMs": round(tr.reasoning_ms)},
                }
            )
        yield sse("[DONE]")
    except Exception:
        logger.exception("turn %s: adapter error", turn.id)
        status, error_code = "failed", "internal"
        for chunk in tr.close():
            yield sse(chunk)
        yield sse({"type": "error", "errorText": "internal"})
        yield sse({"type": "finish", "finishReason": "error"})
        yield sse("[DONE]")
    finally:
        with anyio.CancelScope(shield=True):
            await close_turn(
                engine,
                turn,
                "aborted" if status == "open" else status,
                error_code=error_code,
                reasoning_ms=round(tr.reasoning_ms),
                finish_reason=tr.finish_reason,
                usage=tr.usage,
            )


async def _touch(engine: AsyncEngine, turn: Turn) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            update(chat_turns)
            .where(chat_turns.c.id == turn.id, chat_turns.c.status == "open")
            .values(lease_expires_at=func.now() + LEASE)
        )


async def _reconcile(engine: AsyncEngine, hermes: HermesClient, turn: Turn) -> list[dict]:
    try:
        messages = await hermes.session_messages(turn.hermes_session_id)
    except (httpx.HTTPError, ValueError, KeyError) as e:
        logger.warning("turn %s: reconciliation skipped: %r", turn.id, e)
        return []
    refs = cards.refs_in_tool_messages(cards.messages_of_turn(messages, turn.user_ordinal))
    return await cards.reconcile(engine, turn.id, refs)


@router.post(
    "/chat",
    operation_id="postChat",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}, 404: {}, 409: {}},
)
async def chat(
    req: ChatRequest,
    engine: Annotated[AsyncEngine, Depends(get_engine)],
    hermes: Annotated[HermesClient, Depends(get_hermes)],
) -> StreamingResponse:
    if req.conversationId:
        async with engine.connect() as conn:
            conv = (
                await conn.execute(
                    select(conversations).where(conversations.c.id == req.conversationId)
                )
            ).first()
        if conv is None:
            raise HTTPException(404, {"code": "not_found"})
    else:
        conv_id = new_id("cnv")
        try:
            session_id = await hermes.create_session(conv_id)
        except HermesError as e:
            logger.warning("new conversation: Hermes session not created: %s", e.code)
            stream = offline_stream(new_id("msg"), {"replyLanguage": req.locale})
            return StreamingResponse(
                iter(stream), media_type="text/event-stream", headers=STREAM_HEADERS
            )
        async with engine.begin() as conn:
            await conn.execute(
                insert(conversations).values(
                    id=conv_id, hermes_session_id=session_id, title=title_for(req.message)
                )
            )
            conv = (
                await conn.execute(select(conversations).where(conversations.c.id == conv_id))
            ).one()
    turn = await open_turn(engine, conv, req)
    return StreamingResponse(
        run_turn(engine, hermes, turn, req), media_type="text/event-stream", headers=STREAM_HEADERS
    )


@router.get("/conversations/{conversation_id}/messages", operation_id="getConversationMessages")
async def conversation_messages(
    conversation_id: str,
    engine: Annotated[AsyncEngine, Depends(get_engine)],
    hermes: Annotated[HermesClient, Depends(get_hermes)],
) -> list[dict[str, Any]]:
    async with engine.connect() as conn:
        conv = (
            await conn.execute(select(conversations).where(conversations.c.id == conversation_id))
        ).first()
        if conv is None:
            raise HTTPException(404, {"code": "not_found"})
        turns = {
            r.user_ordinal: r._asdict()
            for r in (
                await conn.execute(
                    select(chat_turns)
                    .where(
                        chat_turns.c.conversation_id == conversation_id,
                        func.coalesce(chat_turns.c.error_code, "").not_like("hermes\\_%"),
                    )
                    .order_by(chat_turns.c.opened_at)
                )
            ).all()
        }
    try:
        messages = await hermes.session_messages(conv.hermes_session_id)
    except httpx.HTTPError as e:
        raise HTTPException(503, {"code": "mona_offline"}) from e

    async def card(ref: str) -> dict[str, Any] | None:
        async with engine.connect() as conn:
            row = (await conn.execute(select(card_events).where(card_events.c.id == ref))).first()
            return row and await cards.card_chunk(conn, row.kind, row.subject)

    return await build_ui_messages(messages, turns, conversation_id, card)

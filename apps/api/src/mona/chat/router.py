"""`POST /api/chat` (the HermesEngine adapter) and the conversation endpoints (C3 §2, §7)."""

from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, literal, select, tuple_
from sqlalchemy.ext.asyncio import AsyncEngine

from mona.api.deps import Feed, FeedLimit, decode_cursor, encode_cursor
from mona.api.errors import ApiFailure, errors
from mona.chat.hermes import HermesClient, get_hermes
from mona.chat.stream import run_turn
from mona.chat.transcript import ui_messages
from mona.chat.turns import TurnInProgress, open_turn
from mona.db import get_engine
from mona.db.models import ChatTurn, Conversation
from mona.dto.base import Dto, Timestamp
from mona.text import norm

router = APIRouter(prefix="/api")

STREAM_HEADERS = {
    "cache-control": "no-cache",
    "connection": "keep-alive",
    "x-vercel-ai-ui-message-stream": "v1",
    "x-accel-buffering": "no",
}
Lang = Literal["en", "fr", "ro"]


class PageContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route: str = Field(max_length=200)
    summary: str = Field(max_length=300)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversationId: str | None = Field(default=None, pattern=r"^cnv_[0-9a-hjkmnp-tv-z]{26}$")
    message: str = Field(min_length=1, max_length=4000)
    pageContext: PageContext
    locale: Lang
    replyLanguage: Lang | None = None

    @field_validator("message", mode="before")
    @classmethod
    def _trimmed(cls, v: Any) -> Any:
        return v.strip() if isinstance(v, str) else v


class ConversationSummary(Dto):
    id: str
    title: str
    last_message_at: Timestamp
    turn_count: int


@router.post(
    "/chat",
    operation_id="postChat",
    response_class=StreamingResponse,
    responses={
        200: {"content": {"text/event-stream": {}}},
        **errors(400, 401, 403, 404, 409, 423),
    },
)
async def chat(
    req: ChatRequest,
    engine: Annotated[AsyncEngine, Depends(get_engine)],
    hermes: Annotated[HermesClient, Depends(get_hermes)],
) -> StreamingResponse:
    if req.conversationId is not None:
        async with engine.connect() as conn:
            found = (
                await conn.execute(
                    select(Conversation.id).where(Conversation.id == req.conversationId)
                )
            ).first()
        if found is None:
            raise ApiFailure(404, "not_found", "No conversation with that id.")
    try:
        turn = await open_turn(
            engine, req.conversationId, req.message, req.locale, req.replyLanguage
        )
    except TurnInProgress:
        raise ApiFailure(
            409, "turn_in_progress", "Mona is still answering in this conversation."
        ) from None
    return StreamingResponse(
        run_turn(engine, hermes, turn, req.pageContext.route, req.pageContext.summary),
        media_type="text/event-stream",
        headers=STREAM_HEADERS,
    )


@router.get("/conversations", operation_id="listConversations", responses=errors(400, 401, 423))
async def conversations(
    engine: Annotated[AsyncEngine, Depends(get_engine)],
    q: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    cursor: Annotated[str | None, Query(max_length=400)] = None,
    limit: FeedLimit = 30,
) -> Feed[ConversationSummary]:
    """C2 §13: newest `lastMessageAt` first; `q` matches `norm(title)`."""
    after = decode_cursor(cursor, {"q": q})
    turns = (
        select(func.count(ChatTurn.id))
        .where(ChatTurn.conversation_id == Conversation.id)
        .scalar_subquery()
    )
    stmt = select(Conversation.id, Conversation.title, Conversation.last_message_at, turns)
    if after is not None:
        at, cid = datetime.fromisoformat(after[0]), after[1]
        stmt = stmt.where(
            tuple_(Conversation.last_message_at, Conversation.id) < tuple_(literal(at), cid)
        )
    stmt = stmt.order_by(Conversation.last_message_at.desc(), Conversation.id.desc())
    wanted = norm(q) if q else None
    items: list[ConversationSummary] = []
    async with engine.connect() as conn:
        for r in (await conn.execute(stmt)).all():
            if wanted and wanted not in norm(r[1]):
                continue
            items.append(
                ConversationSummary(id=r[0], title=r[1], last_message_at=r[2], turn_count=r[3])
            )
            if len(items) > limit:
                break
    more = len(items) > limit
    items = items[:limit]
    last = items[-1] if more else None
    next_cursor = (
        encode_cursor([last.last_message_at.isoformat(), last.id], {"q": q}) if last else None
    )
    return Feed[ConversationSummary](items=items, next_cursor=next_cursor)


@router.get(
    "/conversations/{conversation_id}/messages",
    operation_id="getConversationMessages",
    responses=errors(401, 404, 423),
)
async def conversation_messages(
    conversation_id: str, engine: Annotated[AsyncEngine, Depends(get_engine)]
) -> list[dict[str, Any]]:
    async with engine.connect() as conn:
        found = (
            await conn.execute(select(Conversation.id).where(Conversation.id == conversation_id))
        ).first()
        if found is None:
            raise ApiFailure(404, "not_found", "No conversation with that id.")
        return await ui_messages(conn, conversation_id)

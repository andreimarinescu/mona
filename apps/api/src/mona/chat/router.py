"""`POST /api/chat` (the HermesEngine adapter) and the conversation endpoints (C3 §2, §7)."""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from mona.chat.hermes import HermesClient, get_hermes
from mona.chat.stream import run_turn
from mona.chat.transcript import ui_messages
from mona.chat.turns import TurnInProgress, open_turn
from mona.db import get_engine
from mona.db.models import ChatTurn, Conversation
from mona.dto.base import Dto, Timestamp

router = APIRouter(prefix="/api")

MAX_BODY = 32 * 1024
STREAM_HEADERS = {
    "cache-control": "no-cache",
    "connection": "keep-alive",
    "x-vercel-ai-ui-message-stream": "v1",
    "x-accel-buffering": "no",
}
Lang = Literal["en", "fr", "ro"]


class ApiFailure(Exception):
    """An error before any stream byte, as `{"error": {"code", "message"}}` (C3 §2)."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message

    def response(self) -> JSONResponse:
        body = {"error": {"code": self.code, "message": self.message}}
        return JSONResponse(body, status_code=self.status)


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


class ApiError(BaseModel):
    code: str
    message: str


class ErrorBody(BaseModel):
    error: ApiError


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
        400: {"model": ErrorBody},
        404: {"model": ErrorBody},
        409: {"model": ErrorBody},
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


@router.get("/conversations", operation_id="listConversations")
async def conversations(
    engine: Annotated[AsyncEngine, Depends(get_engine)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ConversationSummary]:
    turns = (
        select(func.count(ChatTurn.id))
        .where(ChatTurn.conversation_id == Conversation.id)
        .scalar_subquery()
    )
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                select(Conversation.id, Conversation.title, Conversation.last_message_at, turns)
                .order_by(Conversation.last_message_at.desc(), Conversation.id.desc())
                .limit(limit)
            )
        ).all()
    return [
        ConversationSummary(id=r[0], title=r[1], last_message_at=r[2], turn_count=r[3])
        for r in rows
    ]


@router.get(
    "/conversations/{conversation_id}/messages",
    operation_id="getConversationMessages",
    responses={404: {"model": ErrorBody}},
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

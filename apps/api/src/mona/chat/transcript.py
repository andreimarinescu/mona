"""Transcript reload from `chat_turns` only (C3 §7.2); Hermes is never called."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection

from mona.chat.cards import card_chunk
from mona.db.models import ChatTurn
from mona.dto.load import SUBJECT_KEYS


def _ui_part(part: dict[str, Any]) -> dict[str, Any] | None:
    kind = part.get("type")
    if kind in ("reasoning", "text"):
        return {"type": kind, "text": part["text"], "state": "done"}
    if kind == "tool":
        out = {
            "type": "dynamic-tool",
            "toolName": part["tool_name"],
            "toolCallId": part["tool_call_id"],
            "input": {},
        }
        if part.get("completed"):
            return {**out, "state": "output-available", "output": {"status": "completed"}}
        return {**out, "state": "output-error", "errorText": "stream_interrupted"}
    return None


async def _assistant_parts(conn: AsyncConnection, stored: list[dict[str, Any]]) -> list[dict]:
    out: list[dict[str, Any]] = []
    cards: dict[tuple[str, str], int] = {}
    for part in stored:
        if part.get("type") != "data":
            ui = _ui_part(part)
            if ui is not None:
                out.append(ui)
            continue
        key = (part["kind"], part["id"])
        if key in cards:
            continue
        chunk = await card_chunk(
            conn, part["kind"], {SUBJECT_KEYS.get(part["kind"], ""): part["id"]}
        )
        if chunk is None:
            continue
        cards[key] = len(out)
        out.append(chunk)
    return out


async def ui_messages(conn: AsyncConnection, conversation_id: str) -> list[dict[str, Any]]:
    turns = (
        await conn.execute(
            select(ChatTurn)
            .where(ChatTurn.conversation_id == conversation_id)
            .order_by(ChatTurn.opened_at, ChatTurn.id)
        )
    ).all()
    out: list[dict[str, Any]] = []
    for t in turns:
        out.append(
            {"id": f"{t.id}:u", "role": "user", "parts": [{"type": "text", "text": t.user_text}]}
        )
        if not t.parts:
            continue
        out.append(
            {
                "id": t.ui_message_id,
                "role": "assistant",
                "metadata": {
                    "conversationId": conversation_id,
                    "turnId": t.id,
                    "replyLanguage": t.reply_language,
                    "reasoningMs": t.reasoning_ms,
                },
                "parts": await _assistant_parts(conn, t.parts),
            }
        )
    return out

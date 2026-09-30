"""Transcript reload: Hermes session messages + cards → AI SDK `UIMessage[]` (C3 §7.2)."""

import json
from collections.abc import Awaitable, Callable
from typing import Any

from mona.chat.cards import CARD_REF
from mona.chat.translate import strip_tool_name

Chunk = dict[str, Any]
CardLookup = Callable[[str], Awaitable[Chunk | None]]


def _args(raw: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(raw or "{}")
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


async def build_ui_messages(
    messages: list[dict[str, Any]],
    turns: dict[int, dict[str, Any]],
    conversation_id: str,
    card: CardLookup,
) -> list[dict[str, Any]]:
    """`turns` maps user_ordinal → {id, ui_message_id, reply_language, reasoning_ms}."""
    out: list[dict[str, Any]] = []
    assistant: dict[str, Any] | None = None
    seen_cards: set[tuple[str, str]] = set()
    ordinal = 0
    for m in messages:
        role = m.get("role")
        if role == "user":
            ordinal += 1
            turn = turns.get(ordinal)
            uid = f"{turn['id']}:u" if turn else f"{conversation_id}:{m.get('id')}:u"
            out.append(
                {"id": uid, "role": "user", "parts": [{"type": "text", "text": m["content"]}]}
            )
            assistant, seen_cards = None, set()
            continue
        if role not in ("assistant", "tool"):
            continue
        if assistant is None:
            turn = turns.get(ordinal) or {}
            assistant = {
                "id": turn.get("ui_message_id") or f"{conversation_id}:{m.get('id')}:a",
                "role": "assistant",
                "parts": [],
                "metadata": {
                    "conversationId": conversation_id,
                    "turnId": turn.get("id"),
                    "replyLanguage": turn.get("reply_language"),
                    "reasoningMs": turn.get("reasoning_ms"),
                },
            }
            out.append(assistant)
        parts = assistant["parts"]
        if role == "assistant":
            if m.get("reasoning_content"):
                parts.append({"type": "reasoning", "text": m["reasoning_content"], "state": "done"})
            for call in m.get("tool_calls") or []:
                fn = call.get("function") or {}
                parts.append(
                    {
                        "type": "dynamic-tool",
                        "toolName": strip_tool_name(fn.get("name", "")),
                        "toolCallId": call.get("id"),
                        "state": "output-available",
                        "input": _args(fn.get("arguments")),
                        "output": {"status": "completed"},
                    }
                )
            if m.get("content"):
                parts.append({"type": "text", "text": m["content"], "state": "done"})
        else:
            for ref in dict.fromkeys(CARD_REF.findall(m.get("content") or "")):
                chunk = await card(ref)
                if chunk is None or (chunk["type"], chunk["id"]) in seen_cards:
                    continue
                seen_cards.add((chunk["type"], chunk["id"]))
                parts.append(chunk)
    return out

"""One chat turn: Hermes upstream → UI Message Stream downstream (C3 §3, §4, §5)."""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import aclosing
from typing import Any

import anyio
import httpx
from sqlalchemy.ext.asyncio import AsyncEngine

from mona.chat import cards
from mona.chat.hermes import HermesClient, HermesError
from mona.chat.overlay import build_overlay
from mona.chat.parts import PartsRecorder
from mona.chat.translate import SSEParser, Translator
from mona.chat.turns import Turn, close_turn, touch

logger = logging.getLogger(__name__)

FIRST_BYTE_S = 30.0
IDLE_S = 120.0
TURN_S = 300.0
KEEPALIVE_S = 15.0
LEASE_TOUCH_S = 10.0

KEEPALIVE = ": keepalive\n\n"
DONE = "data: [DONE]\n\n"


def sse(chunk: dict[str, Any]) -> str:
    return f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"


async def upstream_events(
    hermes: HermesClient, session_id: str, messages: list[dict[str, str]]
) -> AsyncIterator[tuple[str, Any]]:
    """("line", str) | ("idle", None) every KEEPALIVE_S of silence, then one terminal event:
    ("offline", error_code) before any byte, ("broken", reason) after, or ("eof", None)."""
    queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

    async def pump() -> None:
        try:
            async with hermes.stream_completion(session_id, messages) as lines:
                async for line in lines:
                    await queue.put(("line", line))
            await queue.put(("eof", None))
        except HermesError as e:
            await queue.put(("offline", e.code))
        except (httpx.HTTPError, OSError) as e:
            await queue.put(("broken", type(e).__name__))

    clock = asyncio.get_running_loop().time
    task = asyncio.create_task(pump())
    started = last_event = last_beat = clock()
    got_first = False
    try:
        while True:
            limit = started + TURN_S
            limit = min(limit, last_event + IDLE_S if got_first else started + FIRST_BYTE_S)
            wait = max(0.0, min(limit, last_beat + KEEPALIVE_S) - clock())
            try:
                kind, value = await asyncio.wait_for(queue.get(), wait)
            except TimeoutError:
                if clock() >= limit:
                    yield ("broken", "timeout") if got_first else ("offline", "hermes_unreachable")
                    return
                last_beat = clock()
                yield ("idle", None)
                continue
            if kind != "line":
                if kind == "offline" and got_first:
                    kind, value = "broken", value
                yield (kind, value)
                return
            got_first = True
            last_event = last_beat = clock()
            yield (kind, value)
    finally:
        task.cancel()
        with anyio.CancelScope(shield=True):
            await asyncio.gather(task, return_exceptions=True)


async def _reconcile(engine: AsyncEngine, hermes: HermesClient, turn: Turn) -> list[dict]:
    try:
        messages = await hermes.session_messages(turn.conversation_id)
    except (httpx.HTTPError, ValueError, KeyError) as e:
        logger.warning("turn %s: reconciliation skipped: %s", turn.id, type(e).__name__)
        return []
    mine = cards.messages_of_turn(messages, turn.user_text)
    if mine is None:
        logger.warning("turn %s: Hermes' last user message isn't this turn's", turn.id)
        return []
    return await cards.reconcile(engine, turn.id, cards.refs_in_tool_messages(mine))


async def run_turn(
    engine: AsyncEngine, hermes: HermesClient, turn: Turn, route: str, summary: str
) -> AsyncIterator[str]:
    rec, tr, parser = PartsRecorder(), Translator(), SSEParser()
    status, error_code, release = "open", None, False
    loop_time = asyncio.get_running_loop().time
    last_touch = loop_time()

    def out(chunk: dict[str, Any]) -> str:
        rec.record(chunk)
        return sse(chunk)

    def offline_tail() -> list[str]:
        return [
            sse({"type": "error", "errorText": "mona_offline"}),
            sse({"type": "finish-step"}),
            sse({"type": "finish", "finishReason": "error"}),
            DONE,
        ]

    try:
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
        if turn.needs_session:
            try:
                await hermes.ensure_session(turn.conversation_id)
            except HermesError as e:
                logger.warning("turn %s: Hermes session not created: %s", turn.id, e.code)
                status, error_code, release = "failed", e.code, True
                for frame in offline_tail():
                    yield frame
                return
        overlay = build_overlay(
            route, summary, turn.reply_language, turn.notes, pinned=turn.language_pinned
        )
        upstream = [
            {"role": "system", "content": overlay},
            {"role": "user", "content": turn.user_text},
        ]
        try:
            async with aclosing(upstream_events(hermes, turn.conversation_id, upstream)) as events:
                async for kind, value in events:
                    if kind == "idle":
                        yield KEEPALIVE
                        continue
                    if kind == "offline":
                        logger.warning("turn %s: Hermes unreachable: %s", turn.id, value)
                        status, error_code, release = "failed", value, True
                        for frame in offline_tail():
                            yield frame
                        return
                    if kind != "line":
                        logger.warning("turn %s: upstream ended early: %s", turn.id, value)
                        break
                    if loop_time() - last_touch >= LEASE_TOUCH_S:
                        last_touch = loop_time()
                        await touch(engine, turn)
                    ev = parser.feed(value)
                    if ev is None:
                        continue
                    if ev.comment:
                        yield KEEPALIVE
                        continue
                    for chunk in tr.feed(ev):
                        yield out(chunk)
                        if chunk["type"] == "tool-output-available":
                            for card in await cards.emit_pending(
                                engine, turn.id, tr.completed_tools
                            ):
                                yield out(card)
                    if tr.done:
                        break
        except ValueError:
            logger.warning("turn %s: unparseable upstream chunk", turn.id)

        for chunk in tr.close():
            yield out(chunk)
        for card in await cards.emit_pending(engine, turn.id, tr.completed_tools):
            yield out(card)
        for card in await _reconcile(engine, hermes, turn):
            yield out(card)
        if not tr.done:
            status, error_code = "failed", "stream_interrupted"
            yield sse({"type": "error", "errorText": "stream_interrupted"})
            yield sse({"type": "finish", "finishReason": "error"})
        elif tr.finish_reason == "error":
            status, error_code = "failed", "hermes_agent_error"
            if not rec.text_emitted:
                release = True
                for frame in offline_tail()[:-1]:
                    yield frame
            else:
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
        yield DONE
    except Exception:
        logger.exception("turn %s: adapter error", turn.id)
        status, error_code = "failed", "internal"
        for chunk in tr.close():
            yield out(chunk)
        yield sse({"type": "error", "errorText": "internal"})
        yield sse({"type": "finish", "finishReason": "error"})
        yield DONE
    finally:
        with anyio.CancelScope(shield=True):
            await close_turn(
                engine,
                turn,
                "aborted" if status == "open" else status,
                parts=rec.parts,
                release_notes=release,
                error_code=error_code,
                reasoning_ms=round(tr.reasoning_ms) if tr.reasoning_ms else None,
                finish_reason=tr.finish_reason,
                usage=tr.usage,
            )

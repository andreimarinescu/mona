"""Hermes `/v1/chat/completions` SSE → AI SDK UI Message Stream chunks (C3 §4.3)."""

import json
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

Chunk = dict[str, Any]

TOOL_PROGRESS = "hermes.tool.progress"


@dataclass(frozen=True)
class SSEEvent:
    event: str | None
    data: str | None
    comment: bool = False


class SSEParser:
    """Line-at-a-time SSE parser: `event:` names the next `data:` line; `:` lines are comments."""

    def __init__(self) -> None:
        self._event: str | None = None

    def feed(self, line: str) -> SSEEvent | None:
        line = line.rstrip("\r\n")
        if not line:
            self._event = None
            return None
        if line.startswith(":"):
            return SSEEvent(None, None, comment=True)
        if line.startswith("event:"):
            self._event = line[6:].strip()
            return None
        if line.startswith("data:"):
            ev = SSEEvent(self._event, line[5:].lstrip())
            self._event = None
            return ev
        return None


def strip_tool_name(tool: str) -> str:
    if tool.startswith("mcp__"):
        _, _, rest = tool[5:].partition("__")
        return rest or tool
    return tool


class Translator:
    """Stateful mapper; `feed` returns the downstream chunks for one upstream event."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._reasoning: str | None = None
        self._text: str | None = None
        self._reasoning_n = 0
        self._text_n = 0
        self._reasoning_started = 0.0
        self.reasoning_ms = 0.0
        self._running: set[str] = set()
        self.completed_tools: list[str] = []
        self.finish_reason: str | None = None
        self.usage: dict[str, Any] | None = None
        self.done = False

    def feed(self, ev: SSEEvent) -> list[Chunk]:
        if ev.comment or ev.data is None:
            return []
        if ev.data == "[DONE]":
            self.done = True
            return self.close()
        payload = json.loads(ev.data)
        if ev.event == TOOL_PROGRESS:
            return self._tool(payload)
        if ev.event is not None:
            return []
        out: list[Chunk] = []
        for choice in payload.get("choices", []):
            delta = choice.get("delta") or {}
            if delta.get("reasoning_content"):
                out += self._reasoning_delta(delta["reasoning_content"])
            if delta.get("content"):
                out += self._text_delta(delta["content"])
            if choice.get("finish_reason"):
                self.finish_reason = choice["finish_reason"]
        if payload.get("usage"):
            self.usage = payload["usage"]
        return out

    def close(self) -> list[Chunk]:
        return self._end_text() + self._end_reasoning()

    @property
    def ui_finish_reason(self) -> str:
        return self.finish_reason if self.finish_reason in ("stop", "length") else "other"

    def _reasoning_delta(self, delta: str) -> list[Chunk]:
        out = self._end_text()
        if self._reasoning is None:
            self._reasoning_n += 1
            self._reasoning = f"r{self._reasoning_n}"
            self._reasoning_started = self._clock()
            out.append({"type": "reasoning-start", "id": self._reasoning})
        out.append({"type": "reasoning-delta", "id": self._reasoning, "delta": delta})
        return out

    def _text_delta(self, delta: str) -> list[Chunk]:
        out = self._end_reasoning()
        if self._text is None:
            self._text_n += 1
            self._text = f"t{self._text_n}"
            out.append({"type": "text-start", "id": self._text})
        out.append({"type": "text-delta", "id": self._text, "delta": delta})
        return out

    def _end_reasoning(self) -> list[Chunk]:
        if self._reasoning is None:
            return []
        rid, self._reasoning = self._reasoning, None
        self.reasoning_ms += (self._clock() - self._reasoning_started) * 1000
        return [{"type": "reasoning-end", "id": rid}]

    def _end_text(self) -> list[Chunk]:
        if self._text is None:
            return []
        tid, self._text = self._text, None
        return [{"type": "text-end", "id": tid}]

    def _tool(self, p: dict[str, Any]) -> list[Chunk]:
        call_id, name = p.get("toolCallId"), strip_tool_name(p.get("tool", ""))
        if not call_id:
            return []
        started = {
            "type": "tool-input-available",
            "toolCallId": call_id,
            "toolName": name,
            "input": {},
            "dynamic": True,
        }
        if p.get("status") == "running":
            self._running.add(call_id)
            return self.close() + [started]
        if p.get("status") == "completed":
            out = self.close()
            if call_id not in self._running:
                out.append(started)
            self._running.discard(call_id)
            self.completed_tools.append(name)
            out.append(
                {
                    "type": "tool-output-available",
                    "toolCallId": call_id,
                    "output": {"status": "completed"},
                    "dynamic": True,
                }
            )
            return out
        return []


def translate_lines(
    lines: Iterable[str], clock: Callable[[], float] = time.monotonic
) -> list[Chunk]:
    """Upstream SSE lines in, downstream chunks out (no cards, no framing)."""
    parser, tr, out = SSEParser(), Translator(clock), []
    for line in lines:
        ev = parser.feed(line)
        if ev is not None:
            out += tr.feed(ev)
    return out

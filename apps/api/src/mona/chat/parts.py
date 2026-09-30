"""The assistant parts as streamed, stored in `chat_turns.parts` (C3 §7.2)."""

from typing import Any


class PartsRecorder:
    def __init__(self) -> None:
        self.parts: list[dict[str, Any]] = []
        self._open: dict[str, dict[str, Any]] = {}
        self._tools: dict[str, dict[str, Any]] = {}
        self.text_emitted = False

    def record(self, chunk: dict[str, Any]) -> None:
        kind = chunk["type"]
        if kind in ("reasoning-start", "text-start"):
            part = {"type": kind.split("-")[0], "text": ""}
            self._open[chunk["id"]] = part
            self.parts.append(part)
        elif kind in ("reasoning-delta", "text-delta"):
            self._open[chunk["id"]]["text"] += chunk["delta"]
            if kind == "text-delta":
                self.text_emitted = True
        elif kind in ("reasoning-end", "text-end"):
            self._open.pop(chunk["id"], None)
        elif kind == "tool-input-available":
            part = {
                "type": "tool",
                "tool_call_id": chunk["toolCallId"],
                "tool_name": chunk["toolName"],
                "completed": False,
            }
            self._tools[chunk["toolCallId"]] = part
            self.parts.append(part)
        elif kind == "tool-output-available":
            self._tools[chunk["toolCallId"]]["completed"] = True
        elif kind.startswith("data-"):
            self.parts.append({"type": "data", "kind": kind[5:], "id": chunk["id"]})

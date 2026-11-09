"""A40: once a `data-table` card is out, later text loses its markdown-table lines."""

from typing import Any

Chunk = dict[str, Any]


class TableLineGuard:
    """Only the blanks opening a line are held: its first non-blank character decides it."""

    def __init__(self) -> None:
        self.active = False
        self.dropped = 0
        self._part: str | None = None
        self._state = "start"
        self._held = ""

    def feed(self, chunk: Chunk) -> list[Chunk]:
        kind = chunk["type"]
        if kind == "data-table":
            self.active = True
        elif kind == "text-start" and self.active:
            self._part, self._state, self._held = chunk["id"], "start", ""
        elif kind == "text-delta" and chunk["id"] == self._part:
            kept = self._filter(chunk["delta"])
            return [{**chunk, "delta": kept}] if kept else []
        elif kind == "text-end" and chunk["id"] == self._part:
            held, self._part, self._held = self._held, None, ""
            if held:
                return [{"type": "text-delta", "id": chunk["id"], "delta": held}, chunk]
        return [chunk]

    def _filter(self, delta: str) -> str:
        out: list[str] = []
        for ch in delta:
            if self._state == "keep":
                out.append(ch)
                if ch == "\n":
                    self._state = "start"
            elif self._state == "drop":
                if ch == "\n":
                    self._state = "start"
            elif ch == "\n":
                out.append(self._held + ch)
                self._held = ""
            elif ch.isspace():
                self._held += ch
            elif ch == "|":
                self._state, self._held = "drop", ""
                self.dropped += 1
            else:
                out.append(self._held + ch)
                self._state, self._held = "keep", ""
        return "".join(out)

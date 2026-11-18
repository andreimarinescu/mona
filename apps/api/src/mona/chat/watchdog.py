"""A58: a reasoning part that runs too long, repeats itself or stays open too long trips."""

import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass

from mona.chat.translate import OpenReasoning

REPEATS = 5
MIN_LINE = 40
_SPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class Trip:
    reason: str
    chars: int


class ReasoningWatchdog:
    """Rules (a) chars, (b) repeat, (c) time, on the open reasoning part only."""

    def __init__(self, max_chars: int, max_s: float, clock: Callable[[], float]) -> None:
        self._max_chars = max_chars
        self._max_s = max_s
        self._clock = clock
        self._part: str | None = None
        self._read = 0
        self._lines: Counter[str] = Counter()

    def check(self, part: OpenReasoning | None) -> Trip | None:
        if part is None:
            return None
        if part.id != self._part:
            self._part, self._read, self._lines = part.id, 0, Counter()
        if len(part.text) > self._max_chars:
            return Trip("chars", len(part.text))
        if self._repeats(part.text):
            return Trip("repeat", len(part.text))
        if self._clock() - part.opened_at >= self._max_s:
            return Trip("time", len(part.text))
        return None

    def _repeats(self, text: str) -> bool:
        end = text.rfind("\n") + 1
        if end <= self._read:
            return False
        for line in text[self._read : end].splitlines():
            key = _SPACE.sub(" ", line).strip().lower()
            if len(key) >= MIN_LINE:
                self._lines[key] += 1
                if self._lines[key] >= REPEATS:
                    return True
        self._read = end
        return False

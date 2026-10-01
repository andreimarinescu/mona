"""C5 §7 `findQuery`: what the viewer sends to pdf.js find for a verified quote."""

import re

from mona.pipeline.evidence import VALUE_CHECKED, Checked
from mona.text import norm

MAX_CHARS = 120
MIN_RUN_CHARS = 6
_WORD = re.compile(r"\S+")
_EDGES = " \t\n\r\f\v.,;:"
_COLUMN_BREAK = re.compile(r" {2,}")


def columns(page_text: str) -> list[str]:
    """A15: each line's column segments, normalised; a run of ≥ 2 spaces is a column break."""
    return [n for line in page_text.split("\n") for seg in _COLUMN_BREAK.split(line)
            if (n := norm(seg))]  # fmt: skip


def _on_a_line(s: str, lines: list[str]) -> bool:
    n = norm(s)
    return bool(n) and any(n in line for line in lines)


def _longest_run(quote: str, lines: list[str]) -> str | None:
    words = list(_WORD.finditer(quote))
    for size in range(len(words) - 1, 1, -1):
        for i in range(len(words) - size + 1):
            seg = quote[words[i].start() : words[i + size - 1].end()]
            if len(norm(seg)) >= MIN_RUN_CHARS and _on_a_line(seg, lines):
                return seg
    return None


def shape(s: str) -> str | None:
    """Original characters, edges trimmed of whitespace and `.,;:`, one space inside, ≤ 120."""
    s = re.sub(r"\s+", " ", s).strip(_EDGES)
    if len(s) > MAX_CHARS:
        cut = s.rfind(" ", 0, MAX_CHARS + 1)
        s = (s[:cut] if cut > 0 else s[:MAX_CHARS]).strip(_EDGES)
    return s or None


def find_query(c: Checked, page_text: str) -> str | None:
    """`page_text` is the §1.4 text of the verified page; no candidate crosses a column (A15)."""
    if not c.verified:
        return None
    lines = columns(page_text)
    quote = c.field.quote
    if _on_a_line(quote, lines):
        return shape(quote)
    run = _longest_run(quote, lines)
    if run is not None:
        return shape(run)
    if c.token is not None:
        return shape(quote[c.token[0] : c.token[1]])
    if c.field.key not in VALUE_CHECKED and _on_a_line(c.field.value, lines):
        return shape(c.field.value)
    return None

"""A62 item 1.1: the file template that gives one document the name a person wrote for it."""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date

from mona.i18n import MONTHS
from mona.templates.grammar import Part, Token
from mona.templates.render import (
    RenderValues,
    file_date,
    filing_language,
    fold,
    fold_separators,
    format_date,
    literal,
    render,
    slug,
    token_value,
)

SEPARATORS = "-_."
EXTENSION = re.compile(r"\.(?:pdf|jpe?g|png)$", re.IGNORECASE)
UNITS = {"YYYY": "y", "YY": "y", "MMMM": "m", "MM": "m", "DD": "d"}
ORDERS = [("y", "m", "d"), ("d", "m", "y"), ("m", "d", "y"), ("y", "m"), ("m", "y"), ("y",)]
MIN_REFERENCE = 4
MONTH_NAMES = {fold(m).casefold() for names in MONTHS.values() for m in names}


class InferError(ValueError):
    """An `invalid_argument` on the name or the pattern; `hint` names a token or a name."""

    def __init__(self, message: str, *, hint: str | None = None):
        super().__init__(message)
        self.message, self.hint = message, hint


@dataclass(frozen=True)
class Inferred:
    pattern: str
    stem: str


def normalise(example: str) -> str:
    """The example as a C5 §8.4 file name: folded, then steps 2–3; the extension is dropped."""
    return fold_separators(literal(EXTENSION.sub("", example.strip())))


def _ends_at_boundary(stem: str, j: int) -> bool:
    return j == len(stem) or stem[j] in SEPARATORS


def _leading_dates(stem: str, d: date, lang: str) -> Iterator[tuple[int, str, tuple[str, ...]]]:
    """(end, format, unit kinds) of every date format with a year that renders `d` at the
    stem's start, each of year, month and day at most once, starting and ending with a unit."""

    def walk(i: int, fmt: str, kinds: tuple[str, ...]):
        for unit, kind in UNITS.items():
            value = slug(format_date(d, unit, lang))
            if kind in kinds or not stem.startswith(value, i):
                continue
            j, f, k = i + len(value), fmt + unit, (*kinds, kind)
            if "y" in k and _ends_at_boundary(stem, j):
                yield j, f, k
            yield from walk(j, f, k)
            if j < len(stem) and stem[j] in SEPARATORS:
                yield from walk(j + 1, f + stem[j], k)

    yield from walk(0, "", ())


def _leading_date(stem: str, d: date, lang: str) -> tuple[int, str] | None:
    def rank(m: tuple[int, str, tuple[str, ...]]):
        return (-m[0], ORDERS.index(m[2]) if m[2] in ORDERS else len(ORDERS), m[1])

    found = sorted(set(_leading_dates(stem, d, lang)), key=rank)
    return (found[0][0], found[0][1]) if found else None


def _token_text(t: Token) -> str:
    return f"{{{t.name}:{t.format}}}" if t.format else f"{{{t.name}}}"


def check_literals(parts: list[Part], d: date) -> None:
    """A whole literal segment that is a month name or the document's year would repeat in
    every name."""
    for p in parts:
        if not isinstance(p, str):
            continue
        for seg in re.split(r"[-_.\s]+", fold(p)):
            if seg.casefold() in MONTH_NAMES:
                raise InferError(
                    f"'{seg}' is a month name; use {{date:MMMM}} so each document gets its own.",
                    hint="{date:MMMM}",
                )
            if seg == f"{d.year:04d}":
                raise InferError(
                    f"'{seg}' is this document's year; use {{date:YYYY}} so each document gets "
                    "its own.",
                    hint="{date:YYYY}",
                )


def infer(example: str, v: RenderValues) -> Inferred:
    """Longest match, left to right, from token boundaries; ties go date > counterparty >
    entity > sub > reference; everything else is literal. Raises InferError."""
    stem = normalise(example)
    d, lang = file_date(v), filing_language(v)
    lead = _leading_date(stem, d, lang)
    if lead is None:
        raise InferError(f"The name must start with this document's date, {d.isoformat()}.")
    pos, fmt = lead
    parts: list[Part] = [Token("date", fmt, 0)]
    candidates: list[tuple[Token, str]] = [
        (Token("date", "YYYY", 0), slug(format_date(d, "YYYY", lang))),
        (Token("date", "MMMM", 0), slug(format_date(d, "MMMM", lang))),
    ]
    for name in ("counterparty", "entity", "sub", "reference"):
        value = slug(token_value(v, name))
        if value and (name != "reference" or len(value) >= MIN_REFERENCE):
            candidates.append((Token(name, None, 0), value))
    text = ""
    while pos < len(stem):
        if stem[pos - 1] in SEPARATORS:
            hits = [
                (t, value) for t, value in candidates
                if stem.startswith(value, pos) and _ends_at_boundary(stem, pos + len(value))
            ]  # fmt: skip
            if hits:
                t, value = max(hits, key=lambda h: len(h[1]))
                if text:
                    parts.append(text)
                    text = ""
                parts.append(t)
                pos += len(value)
                continue
        text += stem[pos]
        pos += 1
    if text:
        parts.append(text)
    check_literals(parts, d)
    pattern = "".join(p if isinstance(p, str) else _token_text(p) for p in parts)
    got = render("x", pattern, v).file_name.rpartition(".")[0]
    if got != stem:
        raise InferError(f"The pattern {pattern} would name this document {got}.", hint=got)
    return Inferred(pattern, stem)

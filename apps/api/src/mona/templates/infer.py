"""A62 item 1.1: the file template that gives one document the name a person wrote for it."""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date

from mona.i18n import MONTHS
from mona.templates.grammar import Part, TemplateError, Token, parse
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
LEFTOVER_DATE = re.compile(r"[-_.]\d{1,2}(?=[-_.]|$)")
MONTH_ABBREVIATIONS = {
    *("jan", "janv", "ian", "feb", "fev", "fevr", "mar", "apr", "avr", "jun", "iun", "jul"),
    *("juil", "iul", "aug", "sep", "sept", "oct", "nov", "noi", "dec"),
}
MONTH_NAMES = {fold(m).casefold() for names in MONTHS.values() for m in names} | MONTH_ABBREVIATIONS


class InferError(ValueError):
    """An `invalid_argument` on the name or the pattern; `hint` is a pattern or a name."""

    def __init__(self, message: str, *, hint: str | None = None):
        super().__init__(message)
        self.message, self.hint = message, hint


class DateMismatch(InferError):
    """The name doesn't start with this document's date."""


class LiteralError(InferError):
    """A month name or the year as fixed text; `hint` is a pattern without it."""

    def __init__(self, why: str, pattern: str):
        super().__init__(f"{why}; call again with pattern {pattern}.", hint=pattern)
        self.why = why


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
    stem's start, each of year, month and day at most once (a day only with a month),
    starting and ending with a unit."""

    def walk(i: int, fmt: str, kinds: tuple[str, ...]):
        for unit, kind in UNITS.items():
            value = slug(format_date(d, unit, lang))
            if kind in kinds or not stem.startswith(value, i):
                continue
            j, f, k = i + len(value), fmt + unit, (*kinds, kind)
            if "y" in k and ("d" not in k or "m" in k) and _ends_at_boundary(stem, j):
                yield j, f, k
            yield from walk(j, f, k)
            if j < len(stem) and stem[j] in SEPARATORS:
                yield from walk(j + 1, f + stem[j], k)

    yield from walk(0, "", ())


def _leading_date(stem: str, d: date, lang: str) -> tuple[int, str, tuple[str, ...]] | None:
    def rank(m: tuple[int, str, tuple[str, ...]]):
        return (-m[0], ORDERS.index(m[2]) if m[2] in ORDERS else len(ORDERS), m[1])

    found = sorted(set(_leading_dates(stem, d, lang)), key=rank)
    return found[0] if found else None


def _token_text(t: Token) -> str:
    return f"{{{t.name}:{t.format}}}" if t.format else f"{{{t.name}}}"


def check_literals(parts: list[Part], d: date, lang: str) -> None:
    """A whole literal segment that is a month name or the document's year would repeat in
    every name; the hint is the pattern with that segment as its token."""
    for i, p in enumerate(parts):
        if not isinstance(p, str):
            continue
        pieces = re.split(r"([-_.\s]+)", fold(p))
        for n, folded in enumerate(pieces[::2]):
            if folded.casefold() in MONTH_NAMES:
                token = "{date:MMMM}"
                why = (
                    f"'{folded}' is a month name, so every name would get it. Names follow each "
                    f"document's date (this one's month is {format_date(d, 'MMMM', lang)})"
                )
            elif folded == f"{d.year:04d}":
                token = "{date:YYYY}"
                why = f"'{folded}' is this document's year, so every name would get it"
            else:
                continue
            fixed = "".join(token if k == 2 * n else x for k, x in enumerate(pieces))
            pattern = "".join(
                fixed if k == i else x if isinstance(x, str) else _token_text(x)
                for k, x in enumerate(parts)
            )
            raise LiteralError(why, pattern)


def _with_this_month(stem: str, v: RenderValues) -> str | None:
    """The pattern inferred once every month-name segment of the stem is this document's month."""
    month = slug(format_date(file_date(v), "MMMM", filing_language(v)))
    pieces = re.split(r"([-_.])", stem)
    fixed = "".join(
        month if k % 2 == 0 and x.casefold() in MONTH_NAMES else x for k, x in enumerate(pieces)
    )
    if fixed == stem:
        return None
    try:
        return infer(fixed, v).pattern
    except InferError:
        return None


def _expand(example: str, v: RenderValues) -> tuple[str, list[tuple[str, str]]]:
    """Tokens written into an example become this document's values; also returns each
    written token with its slugged value."""
    if "{" not in example and "}" not in example:
        return example, []
    try:
        parts = parse(example, "path")
    except TemplateError as e:
        raise InferError(
            f"The name isn't valid ({e.message} at offset {e.offset}); give it exactly as the "
            "person wrote it."
        ) from None
    written = [
        (_token_text(p), token_value(v, p.name, p.format)) for p in parts if isinstance(p, Token)
    ]
    text = "".join(p if isinstance(p, str) else token_value(v, p.name, p.format) for p in parts)
    return text, [(t, slug(value)) for t, value in written if slug(value)]


def _hits(stem: str, pos: int, candidates: list[tuple[Token, str]]) -> list[tuple[Token, str]]:
    return [
        (t, value) for t, value in candidates
        if stem.startswith(value, pos) and _ends_at_boundary(stem, pos + len(value))
    ]  # fmt: skip


def infer(example: str, v: RenderValues) -> Inferred:
    """Longest match, left to right, from token boundaries; ties go date > counterparty >
    entity > sub > reference; everything else is literal. Raises InferError."""
    expanded, written = _expand(example, v)
    stem = normalise(expanded)
    d, lang = file_date(v), filing_language(v)
    tokens: list[tuple[Token, str]] = []
    for name in ("counterparty", "entity", "sub", "reference"):
        value = slug(token_value(v, name))
        if value and (name != "reference" or len(value) >= MIN_REFERENCE):
            tokens.append((Token(name, None, 0), value))
    lead = _leading_date(stem, d, lang)
    if lead is None or (
        len(lead[2]) < 3
        and LEFTOVER_DATE.match(stem, lead[0])
        and not _hits(stem, lead[0] + 1, tokens)
    ):
        raise DateMismatch(f"The name must start with this document's date, {d.isoformat()}.")
    pos, fmt, _ = lead
    parts: list[Part] = [Token("date", fmt, 0)]
    candidates: list[tuple[Token, str]] = [
        (Token("date", "YYYY", 0), slug(format_date(d, "YYYY", lang))),
        (Token("date", "MMMM", 0), slug(format_date(d, "MMMM", lang))),
        *tokens,
    ]
    text = ""
    while pos < len(stem):
        if stem[pos - 1] in SEPARATORS:
            hits = _hits(stem, pos, candidates)
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
    for token, value in written:
        if any(isinstance(p, str) and value.casefold() in p.casefold() for p in parts):
            raise InferError(
                f"{token} would be the same text in every name; give the name exactly as the "
                "person wrote it, or pass a pattern."
            )
    try:
        check_literals(parts, d, lang)
    except LiteralError as e:
        better = _with_this_month(stem, v)
        if better is None:
            raise
        raise LiteralError(e.why, better) from None
    pattern = "".join(p if isinstance(p, str) else _token_text(p) for p in parts)
    got = render("x", pattern, v).file_name.rpartition(".")[0]
    if got != stem:
        raise InferError(f"The pattern {pattern} would name this document {got}.", hint=got)
    return Inferred(pattern, stem)

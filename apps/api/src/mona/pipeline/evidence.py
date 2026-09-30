"""C5 §6.1 evidence verification: quote on its page (or exactly one other), value in quote."""

import calendar
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from mona.pipeline.schema import Field
from mona.text import _PUNCT, norm

VALUE_CHECKED = ("doc_date", "period_start", "period_end", "due_date", "amount")
UNVERIFIED_CAP = 40
_THOUSANDS = r" \u00a0\u202f.'\u2019"
_RUN = re.compile(rf"[0-9](?:[0-9,{_THOUSANDS}]*[0-9])?")
_GROUP = re.compile(r"[0-9]+")
_COMMA_DECIMAL = re.compile(
    rf"\d{{1,3}}(?:[{_THOUSANDS}]\d{{3}})*(?:,\d{{1,2}})?|\d+(?:,\d{{1,2}})?"
)
_DOT_DECIMAL = re.compile(r"\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?")
_NUMERIC_DATE = re.compile(r"(?<!\d)(\d{1,2})([/.-])(\d{1,2})\2(\d{4}|\d{2})(?!\d)")
_ISO_DATE = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
_YEAR = re.compile(r"(?<!\d)(\d{4})(?!\d)")
MONTHS = {
    **dict.fromkeys(("janvier", "janv", "january", "jan", "ianuarie", "ian"), 1),
    **dict.fromkeys(("fevrier", "fevr", "february", "feb", "februarie"), 2),
    **dict.fromkeys(("mars", "march", "mar", "martie"), 3),
    **dict.fromkeys(("avril", "avr", "april", "apr", "aprilie"), 4),
    **dict.fromkeys(("mai", "may"), 5),
    **dict.fromkeys(("juin", "june", "jun", "iunie", "iun"), 6),
    **dict.fromkeys(("juillet", "juil", "july", "jul", "iulie", "iul"), 7),
    **dict.fromkeys(("aout", "august", "aug"), 8),
    **dict.fromkeys(("septembre", "sept", "september", "sep", "septembrie"), 9),
    **dict.fromkeys(("octobre", "oct", "october", "octombrie"), 10),
    **dict.fromkeys(("novembre", "nov", "november", "noiembrie"), 11),
    **dict.fromkeys(("decembre", "dec", "december", "decembrie"), 12),
}
_MONTH = "|".join(sorted(MONTHS, key=len, reverse=True))
_DAY_MONTH_YEAR = re.compile(
    rf"(?<![0-9a-z])(\d{{1,2}})(?:er)?\s+({_MONTH})(?![a-z])\.?\s+(\d{{4}})(?!\d)"
)
_MONTH_YEAR = re.compile(rf"(?<![0-9a-z])({_MONTH})(?![a-z])\.?\s+(\d{{4}})(?!\d)")

Span = tuple[int, int]


def norm_map(s: str) -> tuple[str, list[int]]:
    """`norm(s)` with, for each output character, the index of the input character it came
    from; lets a match in normalised text be cut from the original characters."""
    chars: list[tuple[str, int]] = []
    for i, c in enumerate(s):
        n = unicodedata.normalize("NFKC", c).translate(_PUNCT)
        n = "".join(x for x in unicodedata.normalize("NFD", n) if unicodedata.category(x) != "Mn")
        chars += [(x, i) for x in n.casefold()]
    out: list[tuple[str, int]] = []
    for x, i in chars:
        if re.match(r"\s", x):
            if not out or out[-1][0] == " ":
                continue
            x = " "
        out.append((x, i))
    while out and out[-1][0] == " ":
        out.pop()
    return "".join(x for x, _ in out), [i for _, i in out]


def _orig(m: re.Match, index: list[int]) -> Span:
    return index[m.start()], index[m.end() - 1] + 1


def _amounts(token: str) -> set[Decimal]:
    out = set()
    if _COMMA_DECIMAL.fullmatch(token):
        digits = re.sub(f"[{_THOUSANDS}]", "", token).replace(",", ".")
        out.add(digits)
    if _DOT_DECIMAL.fullmatch(token):
        out.add(token.replace(",", ""))
    parsed = set()
    for d in out:
        try:
            parsed.add(Decimal(d).quantize(Decimal("0.01")))
        except InvalidOperation:
            pass
    return parsed


def amount_span(quote: str, value: Decimal) -> Span | None:
    """C5 §6.1.1: a number token of the quote, parsed either way, equal to the value."""
    want = value.quantize(Decimal("0.01"))
    for run in _RUN.finditer(quote):
        groups = list(_GROUP.finditer(run.group(0)))
        spans = [(groups[i].start(), groups[j].end()) for i in range(len(groups))
                 for j in range(i, len(groups))]  # fmt: skip
        for a, b in sorted(spans, key=lambda s: s[0] - s[1]):
            if want in _amounts(run.group(0)[a:b]):
                return run.start() + a, run.start() + b
    return None


def _year(y: str) -> int:
    return 2000 + int(y) if len(y) == 2 else int(y)


def _date(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def date_span(quote: str, value: date) -> Span | None:
    for m in _NUMERIC_DATE.finditer(quote):
        if len(m.group(4)) == 2 and m.group(2) != "/":
            continue
        if _date(_year(m.group(4)), int(m.group(3)), int(m.group(1))) == value:
            return m.span()
    for m in _ISO_DATE.finditer(quote):
        if _date(int(m.group(1)), int(m.group(2)), int(m.group(3))) == value:
            return m.span()
    text, index = norm_map(quote)
    for m in _DAY_MONTH_YEAR.finditer(text):
        if _date(int(m.group(3)), MONTHS[m.group(2)], int(m.group(1))) == value:
            return _orig(m, index)
    return None


def period_span(quote: str, value: date, end: bool, fy_end: tuple[int, int] | None) -> Span | None:
    """§6.1.1: `<month> yyyy` for a month's first (start) or last (end) day; a bare `yyyy`
    for 01-01 / 12-31 of that year, or the entity's fiscal year named `yyyy`."""
    text, index = norm_map(quote)
    for m in _MONTH_YEAR.finditer(text):
        y, mo = int(m.group(2)), MONTHS[m.group(1)]
        want = date(y, mo, calendar.monthrange(y, mo)[1] if end else 1)
        if want == value:
            return _orig(m, index)
    for m in _YEAR.finditer(quote):
        y = int(m.group(1))
        wanted = {date(y, 12, 31) if end else date(y, 1, 1)}
        if fy_end:
            fy_close = _date(y, *fy_end)
            fy_prev = _date(y - 1, *fy_end)
            if fy_close and fy_prev:
                wanted.add(fy_close if end else fy_prev + timedelta(days=1))
        if value in wanted:
            return m.span()
    return None


def value_span(f: Field, fy_end: tuple[int, int] | None = None) -> Span | None:
    if f.key == "amount" and f.amount is not None:
        return amount_span(f.quote, f.amount)
    if f.day is None:
        return None
    span = date_span(f.quote, f.day)
    if span is None and f.key in ("period_start", "period_end"):
        span = period_span(f.quote, f.day, f.key == "period_end", fy_end)
    return span


@dataclass(frozen=True)
class Checked:
    field: Field
    page: int
    stated_page: int
    found: bool
    value_ok: bool
    token: Span | None

    @property
    def verified(self) -> bool:
        return self.found and self.value_ok


def locate(quote: str, page: int, pages: Sequence[str]) -> int | None:
    """§6.1 steps 1–3: the stated page, else exactly one other sent page, else None."""
    q = norm(quote)
    if len(q) < 3:
        return None
    normed = [norm(p) for p in pages]
    if 1 <= page <= len(pages) and q in normed[page - 1]:
        return page
    others = [n for n, p in enumerate(normed, 1) if n != page and q in p]
    return others[0] if len(others) == 1 else None


def check(f: Field, pages: Sequence[str], fy_end: tuple[int, int] | None = None) -> Checked:
    """`pages` are the page texts sent to the model (§1.5)."""
    at = locate(f.quote, f.page, pages)
    token = value_span(f, fy_end) if f.key in VALUE_CHECKED else None
    value_ok = f.key not in VALUE_CHECKED or token is not None
    return Checked(f, at or f.page, f.page, at is not None, value_ok, token)


def field_confidence(model_percent: int, verified: bool) -> int:
    return model_percent if verified else min(model_percent, UNVERIFIED_CAP)

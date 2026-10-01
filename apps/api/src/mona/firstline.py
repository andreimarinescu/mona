"""C9 §3.5 and §8 test 4: the Telegram first-line checker. A first line could show on a locked
phone, so it carries no registry name or alias, amount, date or IBAN."""

import re
import unicodedata
from collections.abc import Iterable

from sqlalchemy import Connection, text

from mona.iban import IBAN_PATTERN
from mona.text import contains_word, norm

FIRST_LINE_MAX = 100

_CURRENCY = r"(?:€|\$|£|(?<![a-z])(?:eur|euros?|ron|lei|usd|gbp))"
MONEY = re.compile(
    rf"{_CURRENCY}\s?\d|(?<!\w)\d[\d .,']*\s?{_CURRENCY}(?![a-z])"
    r"|(?<![\d.,])\d{1,3}(?:[ .,]\d{3})*[.,]\d{2}(?!\d)"
)
_EN_MONTHS = (
    "january february march april may june july august september october november december"
    " jan feb mar apr jun jul aug sep sept oct nov dec"
).split()
_FR_RO_MONTHS = (
    "janvier fevrier mars avril mai juin juillet aout septembre octobre novembre decembre"
    " janv fevr avr juil"
    " ianuarie februarie martie aprilie iunie iulie august septembrie octombrie noiembrie"
    " decembrie"
).split()


def _alternatives(words: list[str]) -> str:
    return "(?:" + "|".join(sorted(set(words), key=len, reverse=True)) + r")\.?"


_MONTH, _EN_MONTH = _alternatives(_EN_MONTHS + _FR_RO_MONTHS), _alternatives(_EN_MONTHS)
DATE = re.compile(
    r"(?<!\d)\d{4}-\d{1,2}-\d{1,2}(?!\d)"
    r"|(?<!\d)\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?(?!\d)"
    rf"|(?<![a-z0-9])\d{{1,2}}(?:er|st|nd|rd|th)?\s(?:de\s)?{_MONTH}(?![a-z])"
    rf"|(?<![a-z]){_EN_MONTH}\s\d{{1,2}}(?:st|nd|rd|th)?(?!\d)"
    rf"|(?<![a-z]){_MONTH}\s\d{{4}}(?!\d)"
)


def first_line(message: str) -> str:
    """The text up to the first newline, or the first 100 characters."""
    return message.split("\n", 1)[0][:FIRST_LINE_MAX]


def registry_names(conn: Connection) -> list[str]:
    """Every entity, sub-unit, person and counterparty name and alias, through `norm()`."""
    rows = conn.execute(
        text(
            "SELECT display_name FROM entities UNION ALL SELECT folder_name FROM entities"
            " UNION ALL SELECT unnest(aliases) FROM entities"
            " UNION ALL SELECT label FROM sub_units"
            " UNION ALL SELECT display_name FROM people UNION ALL SELECT short_name FROM people"
            " UNION ALL SELECT unnest(aliases) FROM people"
            " UNION ALL SELECT name FROM counterparties"
            " UNION ALL SELECT alias_norm FROM counterparty_aliases"
        )
    ).scalars()
    return sorted({n for n in (norm(r) for r in rows if r) if n})


def first_line_problems(message: str, names: Iterable[str]) -> list[str]:
    """What the message's first line gives away: `name`, `amount`, `date`, `iban`."""
    line = first_line(message)
    folded = norm(line)
    out = []
    if any(contains_word(folded, n) for n in names):
        out.append("name")
    if MONEY.search(folded):
        out.append("amount")
    if DATE.search(folded):
        out.append("date")
    if IBAN_PATTERN.search(unicodedata.normalize("NFKC", line).upper()):
        out.append("iban")
    return out

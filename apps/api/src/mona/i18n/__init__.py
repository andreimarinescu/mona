"""The server catalog (C8 §1.1): i18next semantics for `{{name}}`, `count` plurals and contexts;
and server-side formatting (C8 §6.4, §7)."""

import json
import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from functools import cache
from pathlib import Path
from typing import Any

LANGS = ("en", "fr", "ro")
LANGUAGE_NAMES = {"en": "English", "fr": "French", "ro": "Romanian"}
NBSP = "\u00a0"

_HERE = Path(__file__).parent
_VAR = re.compile(r"\{\{\s*(\w+)\s*\}\}")
_COMMA_BELOW = str.maketrans("şţŞŢ", "șțȘȚ")

MONTHS = {
    "en": [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ],
    "fr": [
        "janvier",
        "février",
        "mars",
        "avril",
        "mai",
        "juin",
        "juillet",
        "août",
        "septembre",
        "octobre",
        "novembre",
        "décembre",
    ],
    "ro": [
        "ianuarie",
        "februarie",
        "martie",
        "aprilie",
        "mai",
        "iunie",
        "iulie",
        "august",
        "septembrie",
        "octombrie",
        "noiembrie",
        "decembrie",
    ],
}


@cache
def catalog(lang: str) -> dict[str, Any]:
    return json.loads((_HERE / f"{lang}.json").read_text(encoding="utf-8"))


def plural_category(n: int, lang: str) -> str:
    """CLDR cardinal categories for integers (C8 §2.3)."""
    if lang == "fr":
        if n in (0, 1):
            return "one"
        return "many" if n % 1_000_000 == 0 else "other"
    if lang == "ro":
        if n == 1:
            return "one"
        return "few" if n == 0 or 1 <= n % 100 <= 19 else "other"
    return "one" if n == 1 else "other"


def _lookup(lang: str, key: str) -> str | None:
    node: Any = catalog(lang)
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node if isinstance(node, str) else None


def t(key: str, lang: str, *, context: str | None = None, **values: Any) -> str:
    """Resolve `key` (context variant, then plural suffix) and fill `{{name}}`; falls back to
    English, then to the key itself."""
    lang = lang if lang in LANGS else "en"
    candidates = [f"{key}_{context}", key] if context else [key]
    if "count" in values:
        suffix = plural_category(int(values["count"]), lang)
        candidates = [f"{c}_{suffix}" for c in candidates] + candidates
    for lng in (lang, "en"):
        for k in candidates:
            found = _lookup(lng, k)
            if found is not None:
                return _VAR.sub(lambda m: str(values.get(m.group(1), "")), found)
    return key


def ro_comma_below(s: str) -> str:
    """C8 §7 rule 2: cedilla ş ţ Ş Ţ → comma-below ș ț Ș Ț."""
    return s.translate(_COMMA_BELOW)


def format_date(d: date, lang: str) -> str:
    """C8 §6.2 long date: 14 March 2026 / 14 mars 2026 / 14 martie 2026."""
    return f"{d.day} {MONTHS[lang][d.month - 1]} {d.year}"


def format_money(value: Decimal | float, currency: str, lang: str) -> str:
    """C8 §6.2 money: €1,284.60 / 1 284,60 € / 1.284,60 €; RON is written "lei"."""
    q = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    number = f"{q:,.2f}"
    if lang == "fr":
        number = number.replace(",", NBSP).replace(".", ",")
    elif lang == "ro":
        number = number.replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    if currency == "RON":
        return f"{number}{NBSP}lei"
    return f"€{number}" if lang == "en" else f"{number}{NBSP}€"

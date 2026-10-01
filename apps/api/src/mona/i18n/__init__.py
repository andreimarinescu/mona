"""The server catalog (C8 §1.1) and server-side formatting (C8 §6.4, §7)."""

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

_DIR = Path(__file__).parent
_VAR = re.compile(r"\{\{\s*(\w+)\s*\}\}")
_COMMA_BELOW = str.maketrans({"ş": "ș", "ţ": "ț", "Ş": "Ș", "Ţ": "Ț"})

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
    return json.loads((_DIR / f"{lang}.json").read_text(encoding="utf-8"))


def t(key: str, lang: str, **values: Any) -> str:
    """The catalog string for `key` in `lang`, `{{name}}` filled from `values`."""
    node: Any = catalog(lang if lang in LANGS else "en")
    for part in key.split("."):
        node = node[part]
    return _VAR.sub(lambda m: str(values.get(m.group(1), m.group(0))), node)


def ro_comma_below(s: str) -> str:
    """C8 §7 rule 2: cedilla ş/ţ become comma-below ș/ț."""
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

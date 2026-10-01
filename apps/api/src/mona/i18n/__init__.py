"""The server catalog (C8 §1.1): i18next semantics for `{{name}}`, `count` plurals and contexts;
and server-side formatting (C8 §6.4, §7)."""

import json
import re
import unicodedata
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from functools import cache
from pathlib import Path
from typing import Any, Literal, cast

from mona.text import norm

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


_LETTERS = re.compile(r"[^\W\d_]+")
_CUES = {"ro": set("ășşțţ"), "fr": set("éèêëàçùûôœïÿ")}
_WORDS = {
    lang: frozenset(words.split())
    for lang, words in {
        "en": "the and what whats how is are was were did do does we our my me you your of to"
        " for from with about this that these those which when where who due pay paid much many"
        " last next year month week show find open folder please can could have has any all it"
        " its let lets go through questions draft reply remind invoice invoices statement a an"
        " in on at by",
        "fr": "le la les des du de et est sont que quoi qui quel quelle quels quelles combien nous"
        " vous avons avez pour une un au aux ou ce cette ces dans sur avec mon ma mes notre nos"
        " votre vos pas ne il elle je paye payes payee doit echeance echeancier mois annee"
        " derniere dernier redigez rediger reponse demander facture factures releve merci"
        " bonjour passons revue lot en a",
        "ro": "si este sunt ce cat cata cate cati avem aveti pentru nu in pe ca cu aceasta acest"
        " aceste acesti am ati la din anul trecut luna asta cand unde cine care platit platim"
        " plata plati scadent scadenta dumneavoastra va rog documente factura facturile extras"
        " raspuns redactati buna ziua multumesc sa se mi ne al ale lui unei unui acum despre prin"
        " trecem intrebarile de o",
    }.items()
}


Lang = Literal["en", "fr", "ro"]


def detect_language(text: str) -> Lang | None:
    """C8 §4: letter cues from the first and lower-case words (capitalised words are usually
    names), word hits through `norm()`, at least 2 and 1 clear of the runner-up."""
    words = _LETTERS.findall(unicodedata.normalize("NFC", text))
    cue_words = [w.lower() for i, w in enumerate(words) if i == 0 or not w[0].isupper()]
    cues = {lang for lang, marks in _CUES.items() if any(marks & set(w) for w in cue_words)}
    counted = [norm(w) for w in words if len(w) >= 2]
    if len(counted) < 3:
        return cast(Lang, cues.pop()) if len(cues) == 1 else None
    scores = {
        lang: (lang in cues) + sum(w in vocab for w in counted) for lang, vocab in _WORDS.items()
    }
    best, runner_up = sorted(scores.values(), reverse=True)[:2]
    if best < 2 or best - runner_up < 1:
        return None
    return cast(Lang, max(scores, key=scores.__getitem__))

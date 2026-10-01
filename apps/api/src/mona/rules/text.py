"""C5 §4.7 `condition_text` in EN, FR and RO."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from mona.rules.grammar import Condition

LANGS = ("en", "fr", "ro")
NBSP = "\u00a0"
QUOTES = {"en": ("“", "”"), "fr": (f"«{NBSP}", f"{NBSP}»"), "ro": ("„", "”")}
GROUPING = {"en": ",", "fr": NBSP, "ro": "."}
OR = {"en": "or", "fr": "ou", "ro": "sau"}
AND = {"en": "and", "fr": "et", "ro": "și"}
WHEN = {"en": "When {}.", "fr": "Quand {}.", "ro": "Când {}."}

# (field, op) -> lang -> (affirmative, negated); {v} is the rendered value or list.
PHRASES: dict[tuple[str, str], dict[str, tuple[str, str]]] = {
    ("counterparty", "equals"): {
        "en": ("the counterparty is {v}", "the counterparty is not {v}"),
        "fr": ("l'émetteur est {v}", "l'émetteur n'est pas {v}"),
        "ro": ("emitentul este {v}", "emitentul nu este {v}"),
    },
    ("counterparty", "contains"): {
        "en": (
            "the counterparty's name contains {q}",
            "the counterparty's name doesn't contain {q}",
        ),
        "fr": ("le nom de l'émetteur contient {q}", "le nom de l'émetteur ne contient pas {q}"),
        "ro": ("numele emitentului conține {q}", "numele emitentului nu conține {q}"),
    },
    ("text", "contains"): {
        "en": ("the text mentions {q}", "the text doesn't mention {q}"),
        "fr": ("le texte mentionne {q}", "le texte ne mentionne pas {q}"),
        "ro": ("textul menționează {q}", "textul nu menționează {q}"),
    },
    ("doc_type", "equals"): {
        "en": ("it is a {v}", "it isn't a {v}"),
        "fr": ("c'est un(e) {v}", "ce n'est pas un(e) {v}"),
        "ro": ("este de tipul {v}", "nu este de tipul {v}"),
    },
    ("doc_type", "contains"): {
        "en": ("its type contains {q}", "its type doesn't contain {q}"),
        "fr": ("son type contient {q}", "son type ne contient pas {q}"),
        "ro": ("tipul documentului conține {q}", "tipul documentului nu conține {q}"),
    },
    ("category", "equals"): {
        "en": ("Mona reads it as {v}", "Mona doesn't read it as {v}"),
        "fr": ("Mona le lit comme {v}", "Mona ne le lit pas comme {v}"),
        "ro": ("Mona îl încadrează la {v}", "Mona nu îl încadrează la {v}"),
    },
    ("entity", "equals"): {
        "en": ("Mona reads it as {v}", "Mona doesn't read it as {v}"),
        "fr": ("Mona l'attribue à {v}", "Mona ne l'attribue pas à {v}"),
        "ro": ("Mona îl atribuie entității {v}", "Mona nu îl atribuie entității {v}"),
    },
    ("addressee", "contains"): {
        "en": ("it is addressed to {q}", "it isn't addressed to {q}"),
        "fr": ("il est adressé à {q}", "il n'est pas adressé à {q}"),
        "ro": ("este adresat către {q}", "nu este adresat către {q}"),
    },
    ("addressee", "is_person"): {
        "en": ("it is addressed to {v}", "it isn't addressed to {v}"),
        "fr": ("il est adressé à {v}", "il n'est pas adressé à {v}"),
        "ro": ("este adresat către {v}", "nu este adresat către {v}"),
    },
    ("person", "mentions"): {
        "en": ("it names {v}", "it doesn't name {v}"),
        "fr": ("il mentionne {v}", "il ne mentionne pas {v}"),
        "ro": ("în text apare {v}", "în text nu apare {v}"),
    },
    ("iban", "account"): {
        "en": ("it shows the {v} account", "it doesn't show the {v} account"),
        "fr": ("il porte le compte {v}", "il ne porte pas le compte {v}"),
        "ro": ("apare contul {v}", "nu apare contul {v}"),
    },
    ("iban", "entity"): {
        "en": ("it shows one of {v}'s accounts", "it doesn't show any of {v}'s accounts"),
        "fr": ("il porte un compte de {v}", "il ne porte aucun compte de {v}"),
        "ro": ("apare un cont al entității {v}", "nu apare niciun cont al entității {v}"),
    },
    ("siren", "equals"): {
        "en": ("it shows SIREN {v}", "it doesn't show SIREN {v}"),
        "fr": ("il porte le SIREN {v}", "il ne porte pas le SIREN {v}"),
        "ro": ("apare SIREN-ul {v}", "nu apare SIREN-ul {v}"),
    },
    ("siren", "entity"): {
        "en": ("it shows {v}'s SIREN", "it doesn't show {v}'s SIREN"),
        "fr": ("il porte le SIREN de {v}", "il ne porte pas le SIREN de {v}"),
        "ro": ("apare SIREN-ul entității {v}", "nu apare SIREN-ul entității {v}"),
    },
    ("amount", "gt"): {
        "en": ("the amount is over {v}", "the amount is not over {v}"),
        "fr": ("le montant dépasse {v}", "le montant ne dépasse pas {v}"),
        "ro": ("suma depășește {v}", "suma nu depășește {v}"),
    },
    ("amount", "gte"): {
        "en": ("the amount is at least {v}", "the amount is not at least {v}"),
        "fr": ("le montant est d'au moins {v}", "le montant n'est pas d'au moins {v}"),
        "ro": ("suma este de cel puțin {v}", "suma nu este de cel puțin {v}"),
    },
    ("amount", "lt"): {
        "en": ("the amount is under {v}", "the amount is not under {v}"),
        "fr": ("le montant est inférieur à {v}", "le montant n'est pas inférieur à {v}"),
        "ro": ("suma este sub {v}", "suma nu este sub {v}"),
    },
    ("amount", "lte"): {
        "en": ("the amount is at most {v}", "the amount is not at most {v}"),
        "fr": ("le montant est d'au plus {v}", "le montant n'est pas d'au plus {v}"),
        "ro": ("suma este de cel mult {v}", "suma nu este de cel mult {v}"),
    },
    ("amount", "between"): {
        "en": ("the amount is between {a} and {b}", "the amount is not between {a} and {b}"),
        "fr": ("le montant est entre {a} et {b}", "le montant n'est pas entre {a} et {b}"),
        "ro": ("suma este între {a} și {b}", "suma nu este între {a} și {b}"),
    },
}
ALIASES = {
    ("counterparty", "in"): ("counterparty", "equals"),
    ("text", "contains_any"): ("text", "contains"),
    ("text", "contains_all"): ("text", "contains"),
    ("doc_type", "in"): ("doc_type", "equals"),
    ("category", "in"): ("category", "equals"),
    ("entity", "in"): ("entity", "equals"),
    ("addressee", "is_entity"): ("addressee", "is_person"),
    ("siren", "in"): ("siren", "equals"),
}
ENTITY_POSSESSIVE = {("entity", "equals"), ("entity", "in")}


@dataclass
class Names:
    """Display names by key, for rendering references."""

    people: dict[str, str] = field(default_factory=dict)
    entities: dict[str, str] = field(default_factory=dict)
    accounts: dict[str, str] = field(default_factory=dict)  # label + " •• " + last 4
    categories: dict[str, dict[str, str]] = field(default_factory=dict)


def _money(v: float | int, lang: str) -> str:
    """A7: the number part of `format_money` (C8 §6.4), two decimals, no currency."""
    s = f"{Decimal(str(v)):,.2f}"
    if lang == "en":
        return s
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", GROUPING[lang])


def _join(items: list[str], lang: str, conj: dict[str, str]) -> str:
    if len(items) == 1:
        return items[0]
    return f"{', '.join(items[:-1])} {conj[lang]} {items[-1]}"


def _name(c: Condition, v: str, lang: str, names: Names) -> str:
    match (c.field, c.op):
        case ("category", _):
            return names.categories.get(v, {}).get(lang, v)
        case ("entity", _) | ("addressee", "is_entity") | ("iban", "entity") | ("siren", "entity"):
            label = names.entities.get(v, v)
            return f"{label}'s" if (c.field, c.op) in ENTITY_POSSESSIVE and lang == "en" else label
        case ("addressee", "is_person") | ("person", "mentions"):
            return names.people.get(v, v)
        case ("iban", "account"):
            return names.accounts.get(v, v)
    return v


def render_condition(c: Condition, lang: str, names: Names) -> str:
    key = ALIASES.get((c.field, c.op), (c.field, c.op))
    template = PHRASES[key][lang][1 if c.negate else 0]
    if c.field == "amount":
        if c.op == "between":
            return template.format(a=_money(c.value[0], lang), b=_money(c.value[1], lang))
        return template.format(v=_money(c.value, lang))
    open_q, close_q = QUOTES[lang]
    values = c.value if isinstance(c.value, list) else [c.value]
    conj = AND if c.op == "contains_all" else OR
    quoted = _join([f"{open_q}{v}{close_q}" for v in values], lang, conj)
    plain = _join([_name(c, v, lang, names) for v in values], lang, conj)
    return template.format(v=plain, q=quoted)


def render_condition_text(conditions: list[Condition], names: Names) -> dict[str, str]:
    out: dict[str, Any] = {}
    for lang in LANGS:
        phrases = [render_condition(c, lang, names) for c in conditions]
        out[lang] = WHEN[lang].format(_join(phrases, lang, AND))
    return out

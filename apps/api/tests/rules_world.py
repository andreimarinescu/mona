"""A rules-engine World over the C5 §8.5 fictional registry, with synthetic identifiers."""

from datetime import UTC, date, datetime

from mona.iban import iban_hash
from mona.rules.engine import (
    AccountRef,
    CounterpartyRef,
    EntityRef,
    PersonRef,
    RuleSpec,
    Subject,
    SubUnitRef,
    World,
    luhn,
)
from mona.rules.grammar import Condition, RuleAction
from mona.templates import RenderValues
from mona.text import norm
from tests.c5_registry import CATEGORIES, ENTITIES, SUB_UNITS, SUBCATEGORIES, TEMPLATES

SALT = b"s" * 32
IBAN = "FR7630006000011234567890189"
IBAN_SPACED = "FR76 3000 6000 0112 3456 7890 189"
IBAN_BAD = "FR7630006000011234567890188"
STUDIO_SIREN = "888888880"


def siret_of(siren: str) -> str:
    return next(siren + f"{n:05d}" for n in range(100000) if luhn(siren + f"{n:05d}"))


def _cp(key: str, name: str, *aliases: str) -> CounterpartyRef:
    return CounterpartyRef(key, name, norm(name), tuple(norm(a) for a in (name, *aliases)))


WORLD = World(
    people={
        "anna": PersonRef("anna", "Anna Marchand", ("Mme Anna Marchand", "Marchand Anna")),
        "paul": PersonRef("paul", "Paul Marchand", ("M. Paul Marchand",)),
    },
    entities={
        "cabinet": EntityRef("cabinet", "Cabinet Marchand SELARL", ("CABINET MARCHAND",)),
        "studio": EntityRef("studio", "Studio Numérique SASU", (), STUDIO_SIREN),
        "lmnp": EntityRef("lmnp", "LMNP Marchand"),
        "personal": EntityRef("personal", "Personnel"),
    },
    accounts={"lmnp-hello": AccountRef("lmnp-hello", "lmnp", iban_hash(IBAN, SALT))},
    sub_units={
        "lmnp": [SubUnitRef("lmnp", "angers-strasbourg", "Angers-Strasbourg")],
        "personal": [
            SubUnitRef("personal", "anna", "Anna", "anna"),
            SubUnitRef("personal", "paul", "Paul", "paul"),
        ],
    },
    counterparties={
        c.key: c
        for c in [
            _cp("agipi", "AGIPI", "AGIPI Assurance"),
            _cp("hello-bank", "Hello bank", "Hello bank!"),
            _cp("talenz", "TALENZ"),
            _cp("oxyleo", "OXYLEO"),
            _cp("opco", "OPCO"),
            _cp("unim", "UNIM"),
        ]
    },
    subcategories={cat: {k for (c, k) in SUBCATEGORIES if c == cat} for cat in CATEGORIES},
    templates={(cat, None): tpl for cat, tpl in TEMPLATES.items()},
    iban_salt=SALT,
)

T0 = datetime(2026, 9, 1, tzinfo=UTC)


def rule(
    rid: str,
    conditions: list[dict],
    action: dict,
    priority: int | None = None,
    *,
    created: int = 0,
    state: str = "active",
) -> RuleSpec:
    conds = tuple(Condition.model_validate(c) for c in conditions)
    return RuleSpec(
        id=rid,
        priority=priority if priority is not None else 10 * len(conds),
        created_at=T0.replace(minute=created),
        conditions=conds,
        action=RuleAction.model_validate(action),
        state=state,
    )


def render_values(dest, s: Subject, *, counterparty_name: str | None, **kw) -> RenderValues:
    sub_label = SUB_UNITS[(dest.entity, dest.unit)] if dest.unit else None
    sub = SUBCATEGORIES.get((dest.category, dest.subcategory)) if dest.subcategory else None
    return RenderValues(
        entity=ENTITIES[dest.entity],
        arrived_at=datetime(2026, 10, 14, tzinfo=UTC),
        language="fr",
        sub_unit_label=sub_label,
        category_labels=CATEGORIES[dest.category],
        subcategory_labels={"fr": sub, "en": sub, "ro": sub} if sub else None,
        counterparty=counterparty_name,
        **kw,
    )


__all__ = ["IBAN", "IBAN_BAD", "IBAN_SPACED", "STUDIO_SIREN", "WORLD", "date", "rule", "siret_of"]

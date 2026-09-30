"""C5 §9: confidence, penalties, bands and reasons."""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from mona.templates import Token, parse

RULE_BASE = 95
UNVERIFIED_CRITICAL = 20
UNVERIFIED_OTHER = 5
UNVERIFIED_OTHER_CAP = 15
TOKEN_FIELDS = {
    "year": "doc_date",
    "date": "doc_date",
    "fy": "period_end",
    "counterparty": "counterparty",
    "issuer": "issuer",
    "reference": "reference",
}


def tokens_used(path_template: str | None, file_template: str | None) -> set[str]:
    out: set[str] = set()
    for tpl, kind in ((path_template, "path"), (file_template, "file")):
        if tpl:
            out |= {p.name for p in parse(tpl, kind) if isinstance(p, Token)}  # type: ignore[arg-type]
    return out


def band(confidence: int, low: int, high: int) -> str:
    return "high" if confidence >= high else "medium" if confidence >= low else "low"


def percent(model_confidence: float) -> int:
    return int(Decimal(str(model_confidence * 100)).quantize(Decimal(1), ROUND_HALF_UP))


@dataclass(frozen=True)
class Score:
    confidence: int
    band: str
    reasons: tuple[str, ...]


def score(
    *,
    rule_won: bool,
    entity_set: bool,
    model_confidence: float | None,
    category_unknown: bool,
    fields: Mapping[str, bool],
    tokens: set[str],
    fallbacks: Mapping[str, int],
    low: int,
    high: int,
    no_entity: bool = False,
    conflict: bool = False,
    review: bool = False,
) -> Score:
    """`fields`: returned field key → verified. `entity_set`: a rule or the visitor override set
    the entity. `category_unknown`: no category after rules. `no_entity`: no entity, an
    unresolved unit or an unrenderable path."""
    base = RULE_BASE if rule_won else percent(model_confidence or 0)
    if category_unknown:
        base = min(base, low - 1)
    critical = {TOKEN_FIELDS[t] for t in tokens if t in TOKEN_FIELDS}
    if not entity_set:
        critical.add("entity")
    unverified = {k for k, ok in fields.items() if not ok}
    penalty = UNVERIFIED_CRITICAL * len(unverified & critical)
    penalty += sum(fallbacks.values())
    penalty += min(UNVERIFIED_OTHER * len(unverified - critical), UNVERIFIED_OTHER_CAP)
    confidence = max(0, min(100, base - penalty))
    reasons = []
    if no_entity:
        reasons.append("entity")
    if conflict:
        reasons.append("conflict")
    if confidence < low or category_unknown or review:
        reasons.append("low")
    return Score(confidence, band(confidence, low, high), tuple(reasons))

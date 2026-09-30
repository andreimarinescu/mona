"""C5 §4 rule evaluation: conditions, identifier candidates, sub-units, actions, priority."""

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from functools import cached_property

from mona.iban import iban_candidates, iban_hash
from mona.rules.grammar import Condition, RuleAction, UnitFrom
from mona.text import contains_word, norm

_SIREN = re.compile(r"\b[0-9]{3}[ .]?[0-9]{3}[ .]?[0-9]{3}\b")
_SIRET = re.compile(r"\b[0-9]{3}[ .]?[0-9]{3}[ .]?[0-9]{3}[ .]?[0-9]{5}\b")
_DIGITS = re.compile(r"[^0-9]")


def luhn(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch) * (2 if i % 2 else 1)
        total += d - 9 if d > 9 else d
    return total % 10 == 0


def siren_candidates(text: str) -> set[str]:
    """C5 §4.3: Luhn-valid SIRENs, plus the first 9 digits of Luhn-valid SIRETs."""
    t = unicodedata.normalize("NFKC", text)
    out = {d for d in (_DIGITS.sub("", m.group(0)) for m in _SIREN.finditer(t)) if luhn(d)}
    for m in _SIRET.finditer(t):
        d = _DIGITS.sub("", m.group(0))
        if luhn(d):
            out.add(d[:9])
    return out


@dataclass(frozen=True)
class PersonRef:
    key: str
    display_name: str
    aliases: tuple[str, ...] = ()

    def names(self) -> list[str]:
        return [n for n in (norm(x) for x in (self.display_name, *self.aliases)) if n]


@dataclass(frozen=True)
class EntityRef:
    key: str
    display_name: str
    aliases: tuple[str, ...] = ()
    siren: str | None = None

    def names(self) -> list[str]:
        return [n for n in (norm(x) for x in (self.display_name, *self.aliases)) if n]


@dataclass(frozen=True)
class AccountRef:
    key: str
    entity: str
    iban_hash: str


@dataclass(frozen=True)
class SubUnitRef:
    entity: str
    key: str
    label: str
    person: str | None = None


@dataclass(frozen=True)
class CounterpartyRef:
    key: str
    name: str
    name_norm: str
    alias_norms: tuple[str, ...] = ()


@dataclass
class World:
    """The registry rows conditions and actions refer to, by key."""

    people: dict[str, PersonRef] = field(default_factory=dict)
    entities: dict[str, EntityRef] = field(default_factory=dict)
    accounts: dict[str, AccountRef] = field(default_factory=dict)
    sub_units: dict[str, list[SubUnitRef]] = field(default_factory=dict)
    counterparties: dict[str, CounterpartyRef] = field(default_factory=dict)
    subcategories: dict[str, set[str]] = field(default_factory=dict)
    templates: dict[tuple[str, str | None], tuple[str, str]] = field(default_factory=dict)
    iban_salt: bytes = b""

    def template(self, category: str | None, entity: str | None) -> tuple[str, str] | None:
        if category is None:
            return None
        return self.templates.get((category, entity)) or self.templates.get((category, None))


@dataclass
class Subject:
    """What conditions look at for one document (C5 §4.2 "Subject compared")."""

    text: str = ""
    counterparty: str | None = None
    doc_type: str | None = None
    category: str | None = None
    subcategory: str | None = None
    entity: str | None = None
    addressee: str | None = None
    addressee_person: str | None = None
    amount: Decimal | None = None

    @cached_property
    def text_norm(self) -> str:
        return norm(self.text)

    @cached_property
    def sirens(self) -> set[str]:
        return siren_candidates(self.text)

    @cached_property
    def _ibans(self) -> list[str]:
        return iban_candidates(self.text)

    def iban_hashes(self, salt: bytes) -> set[str]:
        return {iban_hash(c, salt) for c in self._ibans}

    @property
    def model_category(self) -> str | None:
        return None if self.category == "unknown" else self.category


class _Unresolved(Exception):
    pass


def _values(c: Condition) -> list:
    return c.value if isinstance(c.value, list) else [c.value]


def _any_word(haystack: str, needles: Iterable[str]) -> bool:
    return any(n and contains_word(haystack, n) for n in needles)


def _ref(table: dict, key: str):
    if key not in table:
        raise _Unresolved(key)
    return table[key]


def _eval(c: Condition, s: Subject, w: World) -> bool:
    vals = _values(c)
    match c.field:
        case "counterparty":
            cp = w.counterparties.get(s.counterparty) if s.counterparty else None
            if cp is None:
                return False
            names = {cp.name_norm, *cp.alias_norms}
            if c.op == "contains":
                return any(_any_word(n, [norm(vals[0])]) for n in names)
            return any(norm(v) in names | {norm(cp.key)} for v in vals)
        case "text":
            hits = [contains_word(s.text_norm, norm(v)) for v in vals if norm(v)]
            if not hits:
                return False
            return all(hits) if c.op == "contains_all" else any(hits)
        case "doc_type":
            if not s.doc_type:
                return False
            t = norm(s.doc_type)
            if c.op == "contains":
                return _any_word(t, [norm(vals[0])])
            return any(t == norm(v) for v in vals)
        case "category":
            cat = s.model_category
            return cat is not None and any(norm(cat) == norm(v) for v in vals)
        case "entity":
            return s.entity is not None and any(s.entity == v for v in vals)
        case "addressee":
            if c.op == "is_person":
                names = _ref(w.people, vals[0]).names()
            elif c.op == "is_entity":
                names = _ref(w.entities, vals[0]).names()
            else:
                names = [norm(vals[0])]
            return bool(s.addressee) and _any_word(norm(s.addressee), names)
        case "person":
            return _any_word(s.text_norm, _ref(w.people, vals[0]).names())
        case "iban":
            if c.op == "account":
                wanted = {_ref(w.accounts, vals[0]).iban_hash}
            else:
                _ref(w.entities, vals[0])
                wanted = {a.iban_hash for a in w.accounts.values() if a.entity == vals[0]}
            return bool(wanted & s.iban_hashes(w.iban_salt))
        case "siren":
            if c.op == "entity":
                siren = _ref(w.entities, vals[0]).siren
                return siren is not None and siren in s.sirens
            return any(v in s.sirens for v in vals)
        case "amount":
            if s.amount is None:
                return False
            a = s.amount
            lo, hi = (Decimal(str(x)) for x in (vals if c.op == "between" else vals * 2))
            return {
                "gt": a > lo,
                "gte": a >= lo,
                "lt": a < lo,
                "lte": a <= lo,
                "between": lo <= a <= hi,
            }[c.op]
    raise AssertionError(c.field)


def holds(c: Condition, s: Subject, w: World) -> bool:
    """C5 §4.2; a missing subject is false before `negate`; a dangling reference is false."""
    try:
        result = _eval(c, s, w)
    except _Unresolved:
        return False
    return not result if c.negate else result


@dataclass(frozen=True)
class RuleSpec:
    id: str
    priority: int
    created_at: datetime
    conditions: tuple[Condition, ...]
    action: RuleAction
    state: str = "active"

    def matches(self, s: Subject, w: World) -> bool:
        return all(holds(c, s, w) for c in self.conditions)


@dataclass(frozen=True)
class Destination:
    entity: str | None
    unit: str | None
    unit_unresolved: bool
    category: str | None
    subcategory: str | None
    path_template: str | None
    file_template: str | None
    counterparty: str | None = None
    review: bool = False

    def key(self) -> tuple:
        """What §4.6.4 compares: entity, unit, category, subcategory, path and file template."""
        return (
            self.entity,
            self.unit,
            self.unit_unresolved,
            self.category,
            self.subcategory,
            self.path_template,
            self.file_template,
        )


def resolve_unit(action: RuleAction, entity: str | None, s: Subject, w: World):
    """C5 §4.4–§4.5: (unit key, unresolved); a sub-unit comes only from the action."""
    if action.unit is None or entity is None:
        return None, False
    if not isinstance(action.unit, UnitFrom):
        return action.unit, False
    units = [u for u in w.sub_units.get(entity, []) if u.person]
    if s.addressee_person:
        linked = [u for u in units if u.person == s.addressee_person]
        if linked:
            return linked[0].key, False
    mentioned = [
        u
        for u in units
        if u.person in w.people and _any_word(s.text_norm, w.people[u.person].names())
    ]
    if len(mentioned) == 1:
        return mentioned[0].key, False
    return None, True


def destination(action: RuleAction, s: Subject, w: World) -> Destination:
    """The action after fallbacks to the model's values (C5 §4.5, §4.6.4)."""
    entity = action.entity or s.entity
    category = action.category or s.model_category
    sub = action.subcategory or s.subcategory
    if sub is not None and sub not in w.subcategories.get(category or "", set()):
        sub = None
    unit, unresolved = resolve_unit(action, entity, s, w)
    tpl = w.template(category, entity)
    return Destination(
        entity=entity,
        unit=unit,
        unit_unresolved=unresolved,
        category=category,
        subcategory=sub,
        path_template=action.path or (tpl[0] if tpl else None),
        file_template=action.filename or (tpl[1] if tpl else None),
        counterparty=action.counterparty,
        review=bool(action.review),
    )


@dataclass(frozen=True)
class Outcome:
    winner: RuleSpec | None
    destination: Destination | None
    conflicting: tuple[str, ...] = ()
    top: tuple[str, ...] = ()
    matched: tuple[str, ...] = ()

    @property
    def conflict(self) -> bool:
        return bool(self.conflicting)


def evaluate(
    rules: Iterable[RuleSpec], s: Subject, w: World, *, as_active: str | None = None
) -> Outcome:
    """C5 §4.6: highest priority wins; equal destinations → oldest; different → conflict.

    `as_active` treats that rule as active whatever its state (§4.6.9 preview and apply)."""
    live = [r for r in rules if r.state == "active" or r.id == as_active]
    m = [r for r in live if r.matches(s, w)]
    if not m:
        return Outcome(None, None)
    top_priority = max(r.priority for r in m)
    t = [r for r in m if r.priority == top_priority]
    dests = {r.id: destination(r.action, s, w) for r in t}
    ids = tuple(r.id for r in t)
    matched = tuple(r.id for r in m)
    if len({d.key() for d in dests.values()}) > 1:
        return Outcome(None, None, conflicting=ids, top=ids, matched=matched)
    winner = min(t, key=lambda r: (r.created_at, r.id))
    return Outcome(winner, dests[winner.id], top=ids, matched=matched)


def learned_priority(n_conditions: int, source_priorities: Iterable[int]) -> int:
    """C5 §4.6.1: `max(10 × n, 1 + P)`, P the highest priority matching the source documents."""
    base = 10 * n_conditions
    p = max(source_priorities, default=None)
    return base if p is None else max(base, p + 1)

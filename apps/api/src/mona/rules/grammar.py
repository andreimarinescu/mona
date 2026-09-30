"""C5 §4 rule grammar: conditions, actions, RuleDraft (structure and references)."""

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    ValidationInfo,
    field_validator,
    model_serializer,
    model_validator,
)

from mona.templates import TemplateError, parse

ConditionField = Literal[
    "counterparty", "text", "doc_type", "category", "entity", "addressee", "person", "iban",
    "siren", "amount",
]  # fmt: skip

# field -> op -> value kind
OPS: dict[str, dict[str, str]] = {
    "counterparty": {"equals": "str", "in": "strs", "contains": "str"},
    "text": {"contains": "str", "contains_any": "strs", "contains_all": "strs"},
    "doc_type": {"equals": "str", "in": "strs", "contains": "str"},
    "category": {"equals": "str", "in": "strs"},
    "entity": {"equals": "str", "in": "strs"},
    "addressee": {"contains": "str", "is_person": "str", "is_entity": "str"},
    "person": {"mentions": "str"},
    "iban": {"account": "str", "entity": "str"},
    "siren": {"equals": "siren", "in": "sirens", "entity": "str"},
    "amount": {"gt": "number", "gte": "number", "lt": "number", "lte": "number",
               "between": "range"},
}  # fmt: skip

SIREN = re.compile(r"[0-9]{9}")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True)

    @model_serializer(mode="wrap")
    def _drop_absent(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        return {k: v for k, v in handler(self).items() if v is not None}


def _is_number(v: object) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool)


class Condition(_Strict):
    field: ConditionField
    op: str
    value: Any
    negate: bool | None = None

    @field_validator("negate")
    @classmethod
    def _negate(cls, v: bool | None) -> bool | None:
        return True if v else None

    @model_validator(mode="after")
    def _check(self) -> "Condition":
        kind = OPS[self.field].get(self.op)
        if kind is None:
            raise ValueError(f"op {self.op!r} is not valid for field {self.field!r}")
        v = self.value
        ok = {
            "str": lambda: isinstance(v, str) and v.strip() != "",
            "strs": lambda: (
                isinstance(v, list)
                and len(v) > 0
                and all(isinstance(x, str) and x.strip() for x in v)
            ),
            "siren": lambda: isinstance(v, str) and SIREN.fullmatch(v) is not None,
            "sirens": lambda: (
                isinstance(v, list)
                and len(v) > 0
                and all(isinstance(x, str) and SIREN.fullmatch(x) for x in v)
            ),
            "number": lambda: _is_number(v),
            "range": lambda: (
                isinstance(v, list)
                and len(v) == 2
                and all(_is_number(x) for x in v)
                and v[0] <= v[1]
            ),
        }[kind]()
        if not ok:
            raise ValueError(f"{self.field} {self.op}: value must be {_KIND_TEXT[kind]}")
        return self


_KIND_TEXT = {
    "str": "a non-empty string",
    "strs": "a non-empty list of strings",
    "siren": "9 digits",
    "sirens": "a non-empty list of 9-digit strings",
    "number": "a number",
    "range": "[min, max] with min <= max",
}


class UnitFrom(_Strict):
    from_: Literal["person"] = Field(alias="from")


class RuleAction(_Strict):
    entity: str | None = None
    unit: str | UnitFrom | None = None
    category: str | None = None
    subcategory: str | None = None
    counterparty: str | None = None
    path: str | None = None
    filename: str | None = None
    review: bool | None = None

    @field_validator("review")
    @classmethod
    def _review(cls, v: bool | None) -> bool | None:
        return True if v else None

    @field_validator("path", "filename")
    @classmethod
    def _template(cls, v: str | None, info: ValidationInfo) -> str | None:
        if v is not None:
            try:
                parse(v, "path" if info.field_name == "path" else "file")
            except TemplateError as e:
                raise ValueError(f"{info.field_name}: {e}") from None
        return v

    @model_validator(mode="after")
    def _check(self) -> "RuleAction":
        if not (self.entity or self.category or self.review):
            raise ValueError("an action needs at least one of entity, category, review")
        if self.unit is not None and not self.entity:
            raise ValueError("unit requires entity")
        return self


class RuleBody(_Strict):
    conditions: list[Condition] = Field(min_length=1, max_length=8)
    action: RuleAction


class RuleDraftBranch(_Strict):
    conditions: list[Condition] = Field(min_length=1, max_length=8)
    action: RuleAction

    @model_validator(mode="after")
    def _entity(self) -> "RuleDraftBranch":
        if not self.action.entity:
            raise ValueError("every branch action names an entity")
        return self


class RuleDraft(BaseModel):
    """C1 §11.5; keys are single words, so this is also the DTO shape."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["always", "depends", "ask"]
    discriminator: ConditionField | None
    branches: list[RuleDraftBranch]

    @model_validator(mode="after")
    def _shape(self) -> "RuleDraft":
        n = len(self.branches)
        if self.kind == "depends":
            if self.discriminator is None:
                raise ValueError("'depends' needs a discriminator")
            if not 2 <= n <= 4:
                raise ValueError("'depends' needs 2-4 branches")
            keys = []
            for b in self.branches:
                on = [c for c in b.conditions if c.field == self.discriminator]
                if not on:
                    raise ValueError(f"every branch needs a condition on {self.discriminator}")
                keys.append(tuple(sorted(repr(c.model_dump()) for c in on)))
            if len(set(keys)) != n:
                raise ValueError(f"branches must differ in their {self.discriminator} condition")
        else:
            if self.discriminator is not None:
                raise ValueError(f"'{self.kind}' takes no discriminator")
            if self.kind == "always" and n != 1:
                raise ValueError("'always' has exactly one branch")
            if self.kind == "ask" and n != 0:
                raise ValueError("'ask' has no branches")
        return self


@dataclass
class Registry:
    """Keys a rule may reference (C5 §4.2.9, §4.5)."""

    entities: set[str] = field(default_factory=set)
    visitors_entity: str | None = None
    sub_units: dict[str, set[str]] = field(default_factory=dict)
    people: set[str] = field(default_factory=set)
    accounts: set[str] = field(default_factory=set)
    counterparties: set[str] = field(default_factory=set)
    categories: set[str] = field(default_factory=set)
    subcategories: dict[str, set[str]] = field(default_factory=dict)


_CONDITION_REFS = {
    ("category", "equals"): "categories",
    ("category", "in"): "categories",
    ("entity", "equals"): "entities",
    ("entity", "in"): "entities",
    ("addressee", "is_person"): "people",
    ("addressee", "is_entity"): "entities",
    ("person", "mentions"): "people",
    ("iban", "account"): "accounts",
    ("iban", "entity"): "entities",
    ("siren", "entity"): "entities",
}

_KIND_NAMES = {
    "categories": "category",
    "entities": "entity",
    "people": "person",
    "accounts": "account",
    "counterparties": "counterparty",
}


def unresolved(body: RuleBody, reg: Registry) -> list[str]:
    """Every reference in `body` that `reg` doesn't hold, as readable messages."""
    out: list[str] = []
    for i, c in enumerate(body.conditions):
        kind = _CONDITION_REFS.get((c.field, c.op))
        if kind:
            values = c.value if isinstance(c.value, list) else [c.value]
            for v in values:
                if v not in getattr(reg, kind):
                    out.append(
                        f"conditions[{i}] {c.field} {c.op}: unknown {_KIND_NAMES[kind]} {v!r}"
                    )
    a = body.action
    if a.entity is not None:
        if a.entity not in reg.entities:
            out.append(f"action.entity: unknown entity {a.entity!r}")
        elif a.entity == reg.visitors_entity:
            out.append("action.entity: the Visitors entity can't be a rule action")
        elif isinstance(a.unit, str) and a.unit not in reg.sub_units.get(a.entity, set()):
            out.append(f"action.unit: unknown sub-unit {a.unit!r} of entity {a.entity!r}")
    if a.category is not None and a.category not in reg.categories:
        out.append(f"action.category: unknown category {a.category!r}")
    if a.subcategory is not None and a.category in reg.categories:
        if a.subcategory not in reg.subcategories.get(a.category, set()):
            out.append(
                f"action.subcategory: unknown subcategory {a.subcategory!r} of {a.category!r}"
            )
    if a.counterparty is not None and a.counterparty not in reg.counterparties:
        out.append(f"action.counterparty: unknown counterparty {a.counterparty!r}")
    return out

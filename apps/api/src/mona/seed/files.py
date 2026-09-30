"""Seed file schemas: practice.yaml (C1 §9) and rules.yaml (C5 §10)."""

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

INVARIANTS = {
    0: "schema",
    1: "keys",
    2: "idempotent",
    3: "no clear IBAN",
    4: "complete labels",
    5: "templates parse",
    6: "rules validate",
    7: "one default template",
    8: "registry only",
}


@dataclass(frozen=True)
class Problem:
    invariant: int
    where: str
    message: str

    def __str__(self) -> str:
        name = INVARIANTS[self.invariant]
        return f"invariant {self.invariant} ({name}): {self.where}: {self.message}"


class SeedError(Exception):
    def __init__(self, problems: list[Problem]):
        self.problems = problems
        super().__init__("seed rejected:\n" + "\n".join(f"  {p}" for p in problems))


class _File(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PracticeInfo(_File):
    name: str
    filing_language: Literal["fr", "en", "ro"] = "fr"
    owner_name: str | None = None
    locale: Literal["en", "fr", "ro"] = "en"
    confidence_high: int | None = None
    confidence_low: int | None = None
    badge_hours: int | None = None
    debrief_queue_threshold: int | None = None


class PersonIn(_File):
    key: str
    display_name: str
    short_name: str | None = None
    aliases: list[str] = []


class SubUnitIn(_File):
    key: str
    label: str
    person: str | None = None


class EntityPersonIn(_File):
    person: str
    role: str | None = None


class EntityIn(_File):
    key: str
    display_name: str
    folder_name: str
    legal_form: str | None = None
    siren: str | None = None
    visibility: Literal["practice", "personal"] = "practice"
    fy_end_month: int = 12
    fy_end_day: int = 31
    filing_language: Literal["fr", "en", "ro"] | None = None
    aliases: list[str] = []
    addresses: list[str] = []
    purge_after_hours: int | None = Field(default=None, gt=0)
    sort_order: int | None = None
    sub_units: list[SubUnitIn] = []
    people: list[EntityPersonIn] = []


class SubcategoryIn(_File):
    key: str
    labels: dict[str, str]
    sort_order: int | None = None


class CategoryIn(_File):
    id: str
    icon: str
    labels: dict[str, str]
    model_definition: str
    sort_order: int | None = None
    subcategories: list[SubcategoryIn] = []


class TemplateIn(_File):
    category: str
    entity: str | None = None
    path_template: str
    file_template: str


class AccountIn(_File):
    key: str
    entity: str
    sub_unit: str | None = None
    label: str
    currency: Literal["EUR", "RON"] = "EUR"
    bank_counterparty: str | None = None
    iban: str


class CounterpartyIn(_File):
    key: str
    name: str
    kind: (
        Literal[
            "supplier",
            "bank",
            "insurer",
            "administration",
            "social",
            "accountant",
            "client",
            "other",
        ]
        | None
    ) = None
    siren: str | None = None
    aliases: list[str] = []


class PracticeFile(_File):
    practice: PracticeInfo
    people: list[PersonIn] = []
    entities: list[EntityIn] = []
    categories: list[CategoryIn] = []
    templates: list[TemplateIn] = []
    accounts: list[AccountIn] = []
    counterparties: list[CounterpartyIn] = []


class RuleStats(_File):
    fired_count: int | None = None
    last_fired_at: Any = None
    corrections_since: int | None = None


class RuleIn(_File):
    key: str
    name: str
    state: Literal["draft", "active", "disabled"] = "active"
    source: Literal["seed", "interview", "correction"] = "seed"
    priority: int | None = None
    conditions: list[Any]
    action: dict[str, Any]
    version: Any = None
    condition_text: Any = None
    stats: RuleStats | None = None


class RulesFile(_File):
    schema_: Literal["mona.rules/v1"] = Field(alias="schema")
    revision: Any = None
    exported_at: Any = None
    rules: list[RuleIn] = []

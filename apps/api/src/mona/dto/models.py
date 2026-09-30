"""C1 §11 DTOs."""

from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Any, ClassVar

from pydantic import Field, field_validator

from mona.dto.base import (
    AccountId,
    BatchId,
    CounterpartyId,
    Day,
    DeadlineId,
    DocId,
    DraftId,
    Dto,
    EntityId,
    ExportId,
    GroupId,
    InterviewId,
    PersonId,
    QuestionId,
    ReminderId,
    RuleId,
    SubUnitId,
    Timestamp,
)
from mona.dto.enums import (
    Actor,
    Band,
    Currency,
    DeadlineStatus,
    DocLocation,
    DocSource,
    DocStatus,
    DraftStatus,
    DsCategory,
    ExportStatus,
    FieldKey,
    GroupKind,
    GroupUndoState,
    InterviewKind,
    InterviewStatus,
    JournalAction,
    Lang,
    PathLocation,
    PipelineStage,
    QuestionStatus,
    Reason,
    RuleSource,
    RuleState,
    UndoState,
    Via,
    Visibility,
)
from mona.rules.grammar import Condition, RuleAction, RuleDraft

Percent = Annotated[int, Field(ge=0, le=100)]

# §11.1


class Money(Dto):
    value: float
    currency: Currency

    @field_validator("value", mode="before")
    @classmethod
    def _round(cls, v: Any) -> float:
        return float(Decimal(str(v)).quantize(Decimal("0.01"), ROUND_HALF_UP))


# §11.2


class Evidence(Dto):
    document_id: DocId
    document_title: str
    field: FieldKey | None
    page: int = Field(ge=1)
    quote: str
    verified: bool
    find_query: str | None


class ExtractedField(Dto):
    omit_if_none: ClassVar[frozenset[str]] = frozenset({"money"})

    key: FieldKey
    value: str
    money: Money | None = None
    evidence: Evidence
    confidence: Percent


# §11.4


class Suggestion(Dto):
    entity_id: EntityId | None
    sub_unit_id: SubUnitId | None
    category_id: str | None
    subcategory_key: str | None
    file_name: str | None
    path: list[str]
    confidence: Percent
    band: Band
    reasons: list[Reason]
    sentence: str
    evidence: list[Evidence]
    rule_id: RuleId | None
    conflicting_rule_ids: list[RuleId]


# §11.5


class Rule(Dto):
    omit_if_none: ClassVar[frozenset[str]] = frozenset({"last_fired_at"})

    id: RuleId
    name: str
    condition: str
    condition_text: str
    conditions: list[Condition]
    action: RuleAction
    destination: list[str]
    enabled: bool
    state: RuleState
    source: RuleSource
    version: int
    priority: int
    fired_count: int
    last_fired_at: Timestamp | None = None
    corrections_since: int


class RuleMove(Dto):
    document_id: DocId
    title: str
    from_: list[str] = Field(alias="from")
    from_file_name: str
    to: list[str]
    to_file_name: str


class RulePreview(Dto):
    rule: Rule
    moves: list[RuleMove]
    moves_total: int
    stays: list[DocId]
    stays_total: int
    applied: bool
    group_id: GroupId | None


# §11.6


class PathState(Dto):
    location: PathLocation
    path: list[str]
    file_name: str
    status: DocStatus


class JournalEntry(Dto):
    omit_if_none: ClassVar[frozenset[str]] = frozenset({"batch_id", "undone_by"})

    id: int
    at: Timestamp
    actor: Actor
    via: Via
    action: JournalAction
    document_ids: list[DocId] = Field(max_length=1)
    subject_id: str | None
    before: PathState | dict[str, Any] | None
    after: PathState | dict[str, Any] | None
    batch_id: BatchId | None = None
    group_id: GroupId | None
    rule_id: RuleId | None
    confidence: Percent | None
    band: Band | None
    undoable: bool
    undo_state: UndoState
    undone_by: int | None = None
    undo_of: int | None


class JournalCounts(Dto):
    entries: int
    undoable: int
    superseded: int
    undone: int


class JournalGroup(Dto):
    id: GroupId
    kind: GroupKind
    at: Timestamp
    actor: Actor
    via: Via
    batch_id: BatchId | None
    rule_id: RuleId | None
    counts: JournalCounts
    undo_state: GroupUndoState
    target_group_id: GroupId | None


# §11.7


class DeadlineReminder(Dto):
    id: ReminderId
    remind_on: Day


class Deadline(Dto):
    omit_if_none: ClassVar[frozenset[str]] = frozenset({"amount", "paid_by"})

    id: DeadlineId
    document_id: DocId | None
    label: str
    entity_id: EntityId
    entity_name: str
    due_date: Day
    amount: Money | None = None
    paid_by: str | None = None
    status: DeadlineStatus
    days_left: int
    reminder: DeadlineReminder | None


class InterviewOption(Dto):
    omit_if_none: ClassVar[frozenset[str]] = frozenset({"suggested"})

    id: str
    label: str
    suggested: bool | None = None
    rule_draft: RuleDraft | None


class InterviewAnswer(Dto):
    option_id: str | None
    free_text: str | None
    rule_ids: list[RuleId]


class InterviewQuestion(Dto):
    id: QuestionId
    ordinal: int = Field(ge=1, le=7)
    question: str
    lang: Lang
    affects: list[DocId]
    affects_count: int
    evidence: list[Evidence]
    options: list[InterviewOption]
    suggestion_confidence: Percent
    status: QuestionStatus
    answer: InterviewAnswer | None


class Interview(Dto):
    id: InterviewId
    kind: InterviewKind
    status: InterviewStatus
    questions: list[InterviewQuestion]
    batch_id: BatchId | None
    created_at: Timestamp


class Draft(Dto):
    id: DraftId
    document_id: DocId
    lang: Lang
    status: DraftStatus
    title: str | None
    body: str | None
    docx_url: str | None


class ExportPack(Dto):
    id: ExportId
    entity_id: EntityId
    entity_name: str
    fiscal_year: int
    status: ExportStatus
    document_count: int | None
    zip_url: str | None
    csv_url: str | None


# §11.3 (after the types it embeds)


class RuleRef(Dto):
    id: RuleId
    name: str


class DocumentSummary(Dto):
    omit_if_none: ClassVar[frozenset[str]] = frozenset({"amount"})

    id: DocId
    title: str
    original_name: str
    file_name: str
    path: list[str]
    location: DocLocation
    entity_id: EntityId | None
    entity_name: str | None
    sub_unit_id: SubUnitId | None
    category_id: str | None
    subcategory_key: str | None
    counterparty_id: CounterpartyId | None
    counterparty: str | None
    doc_type: str | None
    reference: str | None
    date: Day | None
    period_start: Day | None
    period_end: Day | None
    fiscal_year: int | None
    amount: Money | None = None
    due_date: Day | None
    status: DocStatus
    reasons: list[Reason]
    confidence: Percent | None
    band: Band | None
    pipeline_stage: PipelineStage
    arrived_at: Timestamp
    source: DocSource
    filed_at: Timestamp | None
    filed_by: Actor | None
    badge_until: Timestamp | None
    rule: RuleRef | None
    batch_id: BatchId
    page_count: int | None
    thumbnail_url: str | None
    pdf_url: str


class DocumentDetail(DocumentSummary):
    fields: list[ExtractedField]
    suggestion: Suggestion | None
    journal: list[JournalEntry]
    deadlines: list[Deadline]


# §11.8


class LangLabels(Dto):
    en: str
    fr: str
    ro: str


class EntitySubUnit(Dto):
    id: SubUnitId
    key: str
    label: str
    person_id: PersonId | None


class EntityPersonLink(Dto):
    person_id: PersonId
    role: str | None


class EntityAccount(Dto):
    id: AccountId
    key: str
    label: str
    iban_last4: str = Field(pattern=r"^[0-9A-Z]{4}$")
    sub_unit_id: SubUnitId | None


class Entity(Dto):
    id: EntityId
    key: str
    display_name: str
    folder_name: str
    legal_form: str | None
    siren: str | None
    visibility: Visibility
    fiscal_year_end: str = Field(pattern=r"^(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$")
    filing_language: Lang | None
    sub_units: list[EntitySubUnit]
    people: list[EntityPersonLink]
    accounts: list[EntityAccount]


class Person(Dto):
    id: PersonId
    key: str
    display_name: str
    short_name: str | None


class SubcategoryDto(Dto):
    key: str
    labels: LangLabels


class CategoryTemplate(Dto):
    path_template: str
    file_template: str


class EntityTemplate(Dto):
    entity_id: EntityId
    path_template: str
    file_template: str


class Category(Dto):
    id: str
    labels: LangLabels
    icon: DsCategory
    subcategories: list[SubcategoryDto]
    template: CategoryTemplate
    entity_templates: list[EntityTemplate]


class Counterparty(Dto):
    id: CounterpartyId
    key: str
    name: str
    kind: str | None

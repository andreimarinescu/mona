"""C2's endpoint DTOs (camelCase, C1 §1.1), named as the contract names them (C2 §16 item 5)."""

from datetime import date
from typing import Annotated, Any, ClassVar, Literal

from pydantic import Field

from mona.dto.base import Day, Dto, Timestamp
from mona.dto.enums import Band, DocStatus, Lang, Reason
from mona.dto.models import (
    Category,
    Deadline,
    DocumentDetail,
    DocumentSummary,
    Entity,
    JournalEntry,
    JournalGroup,
    Money,
    PathState,
    Person,
    Rule,
    RulePreview,
)
from mona.rules.grammar import Condition, RuleAction

# §3 Shell and Home


class QueueCounts(Dto):
    llm: int
    cpu: int


class ShellState(Dto):
    review_count: int
    processing_count: int
    queue: QueueCounts
    mona: Literal["online", "offline"]


class EntityCount(Dto):
    entity_id: str
    name: str
    count: int


class FiledFacts(Dto):
    count: int
    by_entity: list[EntityCount]


class ReviewFacts(Dto):
    count: int
    by_reason: dict[Reason, int]


class ReminderFact(Dto):
    reminder_id: str
    label: str
    note: str | None


class LearnedFact(Dto):
    rule_id: str
    name: str
    created_at: Timestamp
    fired_since: int


class PendingInterview(Dto):
    interview_id: str
    open_questions: int


class BriefFacts(Dto):
    generated_at: Timestamp
    since: Timestamp
    filed: FiledFacts
    needs_review: ReviewFacts
    due_soon: list[Deadline]
    reminders_today: list[ReminderFact]
    learned: list[LearnedFact]
    pending_interview: PendingInterview | None


class BatchCounts(Dto):
    items: int
    accepted: int
    duplicate: int
    rejected: int
    processing: int
    filed: int
    review: int
    unreadable: int
    failed: int


class BatchDebrief(Dto):
    interview_id: str
    status: Literal["generating", "ready", "done", "failed", "cancelled"]
    open_questions: int


class BatchSummary(Dto):
    id: str
    source: Literal["drop", "telegram", "reclassify"]
    status: Literal["running", "done"]
    title: str | None
    visitor: bool
    started_at: Timestamp
    finished_at: Timestamp | None
    counts: BatchCounts
    group_id: str
    debrief: BatchDebrief | None


class IntakeItem(Dto):
    id: str
    original_name: str
    sha256: str
    size_bytes: int
    outcome: Literal["accepted", "duplicate", "rejected"]
    reject_reason: Literal["unsupported_type", "too_large", "empty", "unreadable_file"] | None
    document_id: str | None
    deleted: bool
    restore_journal_id: int | None


class IntakeResult(Dto):
    batch: BatchSummary
    items: list[IntakeItem]


class BatchItem(IntakeItem):
    document: DocumentSummary | None


class BatchDetail(Dto):
    batch: BatchSummary
    items: list[BatchItem]


class BatchPatch(Dto):
    title: Annotated[str, Field(max_length=120)] | None


class ReviewBlock(Dto):
    total: int
    items: list[DocumentSummary]


class DueBlock(Dto):
    total: int
    items: list[Deadline]


class DocRef(Dto):
    title: str
    file_name: str
    deleted: bool


class RuleName(Dto):
    name: str


class GroupItem(Dto):
    kind: Literal["group"]
    group: JournalGroup
    preview: list[JournalEntry]
    entries_total: int
    redo_group_id: str | None


class EntryItem(Dto):
    kind: Literal["entry"]
    entry: JournalEntry


ActivityItem = Annotated[GroupItem | EntryItem, Field(discriminator="kind")]


class ActivityBlock(Dto):
    items: list[ActivityItem]
    documents: dict[str, DocRef]
    rules: dict[str, RuleName]


class IngestionDay(Dto):
    date: Day
    count: int


class Ingestion(Dto):
    days: list[IngestionDay]
    last_batch: BatchSummary | None


class HomeView(Dto):
    facts: BriefFacts
    journal_entry_count: int
    review: ReviewBlock
    due: DueBlock
    activity: ActivityBlock
    ingestion: Ingestion


# §4 Documents


class FacetEntity(Dto):
    id: str
    name: str
    count: int


class FacetYear(Dto):
    year: int
    count: int


class FacetCategory(Dto):
    id: str
    label: str
    count: int


class FacetStatus(Dto):
    status: DocStatus
    count: int


class AmountRange(Dto):
    min: float | None
    max: float | None


class Facets(Dto):
    entities: list[FacetEntity]
    years: list[FacetYear]
    categories: list[FacetCategory]
    counterparties: list[FacetEntity]
    statuses: list[FacetStatus]
    amount: AmountRange


class DocumentPage(Dto):
    items: list[DocumentSummary]
    total: int
    offset: int
    limit: int
    facets: Facets


class FolderNode(Dto):
    name: str
    path: list[str]
    document_count: int
    has_children: bool


class FolderListing(Dto):
    path: list[str]
    folders: list[FolderNode]
    documents: list[DocumentSummary]


# §6 Review and corrections


class JournalTarget(Dto):
    journal_id: int


class GroupTarget(Dto):
    group_id: str


class FileOpResult(Dto):
    document: DocumentDetail | None
    outcome: Literal["moved", "unchanged"]
    journal_ids: list[int]
    group_id: str | None
    undo: JournalTarget | GroupTarget | None


class CounterpartyById(Dto):
    id: str


class CounterpartyByName(Dto):
    name: Annotated[str, Field(min_length=1, max_length=160)]


class CorrectionRequest(Dto):
    entity_id: str | None = None
    sub_unit_id: str | None = None
    category_id: str | None = None
    subcategory_key: str | None = None
    counterparty: CounterpartyById | CounterpartyByName | None = None
    doc_date: date | None = None
    period_end: date | None = None
    due_date: date | None = None
    amount: Money | None = None


class DeleteRequest(Dto):
    confirm: bool
    file_name: Annotated[str, Field(min_length=1, max_length=400)]


class ConversationRef(Dto):
    conversation_id: str | None = None


class LikeThisResult(Dto):
    rule: Rule
    preview: RulePreview


# §7 Rules


class RuleListItem(Dto):
    rule: Rule
    valid: bool
    problems: list[str]


class RulePatch(Dto):
    name: Annotated[str, Field(min_length=1, max_length=120)] | None = None
    enabled: bool | None = None
    conditions: list[dict[str, Any]] | None = None
    action: dict[str, Any] | None = None
    priority: Annotated[int, Field(ge=0, le=100_000)] | None = None


class FailedMove(Dto):
    document_id: str
    code: str


class ApplyResult(Dto):
    preview: RulePreview
    group_id: str | None
    moved: int
    unchanged: int
    failed: list[FailedMove]


class LearnedItem(Dto):
    rule: Rule
    created_at: Timestamp
    moved: int


# §8 Registry (slugs, labels, icons, SIREN and FY end are checked by the route: 422)

Name = Annotated[str, Field(min_length=1, max_length=160)]
Aliases = list[Annotated[str, Field(min_length=1, max_length=200)]]
Addresses = list[Annotated[str, Field(min_length=1, max_length=300)]]


class EntityWrite(Dto):
    key: str | None = None
    display_name: Name
    folder_name: Annotated[str, Field(min_length=1, max_length=120)]
    legal_form: Annotated[str, Field(max_length=40)] | None = None
    siren: Annotated[str, Field(max_length=20)] | None = None
    visibility: Literal["practice", "personal"]
    fiscal_year_end: str
    filing_language: Lang | None = None
    aliases: Aliases | None = None
    addresses: Addresses | None = None
    purge_after_hours: int | None = None
    sort_order: int | None = None


class EntityPatch(Dto):
    key: str | None = None
    display_name: Name | None = None
    folder_name: Annotated[str, Field(min_length=1, max_length=120)] | None = None
    legal_form: Annotated[str, Field(max_length=40)] | None = None
    siren: Annotated[str, Field(max_length=20)] | None = None
    visibility: Literal["practice", "personal"] | None = None
    fiscal_year_end: str | None = None
    filing_language: Lang | None = None
    aliases: Aliases | None = None
    addresses: Addresses | None = None
    purge_after_hours: int | None = None
    sort_order: int | None = None


class EntityDetail(Entity):
    aliases: list[str]
    addresses: list[str]
    purge_after_hours: int | None
    sort_order: int


class EntityList(Dto):
    items: list[Entity]
    document_counts: dict[str, int]
    visitors_entity_id: str | None


class SubUnitWrite(Dto):
    key: str | None = None
    label: Annotated[str, Field(min_length=1, max_length=120)]
    person_id: str | None = None


class SubUnitPatch(Dto):
    key: str | None = None
    label: Annotated[str, Field(min_length=1, max_length=120)] | None = None
    person_id: str | None = None


class AccountWrite(Dto):
    key: str | None = None
    label: Annotated[str, Field(min_length=1, max_length=120)]
    iban: Annotated[str, Field(min_length=1, max_length=64)]
    currency: Literal["EUR", "RON"]
    sub_unit_id: str | None = None
    bank_counterparty_id: str | None = None


class PersonDetail(Person):
    aliases: list[str]


class PersonList(Dto):
    items: list[PersonDetail]


class PersonWrite(Dto):
    key: str | None = None
    display_name: Name
    short_name: Annotated[str, Field(max_length=80)] | None = None
    aliases: Aliases | None = None


class PersonPatch(Dto):
    key: str | None = None
    display_name: Name | None = None
    short_name: Annotated[str, Field(max_length=80)] | None = None
    aliases: Aliases | None = None


class EntityPersonWrite(Dto):
    role: Annotated[str, Field(max_length=80)] | None = None


class TemplatePair(Dto):
    path_template: Annotated[str, Field(min_length=1, max_length=400)]
    file_template: Annotated[str, Field(min_length=1, max_length=400)]


class CategoryWrite(Dto):
    id: str
    labels: dict[str, str]
    icon: str
    model_definition: Annotated[str, Field(min_length=1, max_length=2000)]
    template: TemplatePair


class CategoryPatch(Dto):
    labels: dict[str, str] | None = None
    icon: str | None = None
    model_definition: Annotated[str, Field(min_length=1, max_length=2000)] | None = None
    template: TemplatePair | None = None


class CategoryList(Dto):
    items: list[Category]
    document_counts: dict[str, int]


class SubcategoryWrite(Dto):
    key: str | None = None
    labels: dict[str, str]


class SubcategoryPatch(Dto):
    labels: dict[str, str]


class TemplatePreviewRequest(Dto):
    path_template: Annotated[str, Field(max_length=400)]
    file_template: Annotated[str, Field(max_length=400)]
    document_id: str | None = None
    entity_id: str | None = None


class TemplateError(Dto):
    template: Literal["path", "file"]
    offset: int
    message: str


class TemplatePreview(Dto):
    path: list[str]
    file_name: str | None
    error: TemplateError | None


# §9 Journal


class ActivityPage(Dto):
    items: list[ActivityItem]
    next_cursor: str | None
    documents: dict[str, DocRef]
    rules: dict[str, RuleName]


class GroupDetail(Dto):
    group: JournalGroup
    entries: list[JournalEntry]
    documents: dict[str, DocRef]


class EntryDetail(Dto):
    entry: JournalEntry
    documents: dict[str, DocRef]


class Undone(Dto):
    journal_id: int
    document_id: str
    title: str
    to: PathState


class Skipped(Dto):
    journal_id: int
    state: Literal["superseded", "already_undone", "not_undoable", "not_allowed"]


class RuleStateChange(Dto):
    rule_id: str
    state: Literal["draft", "active", "disabled"]


class UndoResult(Dto):
    group_id: str | None
    undone: list[Undone]
    skipped: list[Skipped]
    entries: list[JournalEntry]
    rule_states: list[RuleStateChange]


# §15 Settings and system status


class SettingsView(Dto):
    profile_name: str
    locale: Lang
    auto_lock_minutes: int
    practice_name: str
    filing_language: Lang
    confidence_high: int
    confidence_low: int
    badge_hours: int
    debrief_queue_threshold: int
    debrief_early_min: int


class SettingsPatch(Dto):
    profile_name: str | None = None
    locale: Lang | None = None
    auto_lock_minutes: int | None = None
    practice_name: str | None = None
    filing_language: Lang | None = None
    confidence_high: int | None = None
    confidence_low: int | None = None
    badge_hours: int | None = None
    debrief_queue_threshold: int | None = None
    debrief_early_min: int | None = None


class MonaStatus(Dto):
    status: Literal["online", "offline"]
    hermes_version: str | None


class LlmStatus(Dto):
    endpoint: Literal["local", "openrouter"]
    model: str | None
    quantization: str | None
    context_per_slot: int | None
    slots: int | None
    vram_bytes: None


class QueueState(Dto):
    todo: int
    doing: int


class Queues(Dto):
    llm: QueueState
    cpu: QueueState


class Disk(Dto):
    data_free_bytes: int
    data_total_bytes: int


class Privacy(Dto):
    cloud_ai: bool
    telegram: bool


class SystemStatus(Dto):
    version: str
    build: str | None
    env: Literal["dev", "prod"]
    mona: MonaStatus
    llm: LlmStatus
    queues: Queues
    database: Literal["ok", "error"]
    disk: Disk
    privacy: Privacy


__all__ = ["Band", "Condition", "RuleAction", "ClassVar"]

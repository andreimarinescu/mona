"""Result models for the read tools (C4 §3); `extra="forbid"` so a stray key fails validation."""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

CardRef = Annotated[str, Field(pattern=r"^crd_[0-9a-hjkmnp-tv-z]{26}$")]
DocId = Field(pattern=r"^doc_[0-9a-hjkmnp-tv-z]{26}$")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EntityRef(Strict):
    key: str
    name: str


class CategoryRef(Strict):
    id: str
    label: str


class Carded(Strict):
    card_refs: list[CardRef]


class Hit(Strict):
    id: str = DocId
    title: str = Field(max_length=160)
    entity: EntityRef | None
    category: CategoryRef | None
    counterparty: str | None
    date: date | None
    amount: float | None
    currency: Literal["EUR", "RON"] | None
    due_date: date | None
    status: Literal["filed", "review", "unreadable"]


class SearchResult(Carded):
    total: int
    next_cursor: str | None
    results: list[Hit]
    truncated: bool = False


class RuleRef(Strict):
    id: str
    name: str


class DocumentResult(Carded):
    id: str = DocId
    title: str
    status: Literal["processing", "filed", "review", "unreadable"]
    entity: EntityRef | None
    sub_unit: str | None
    category: CategoryRef | None
    subcategory: str | None
    counterparty: str | None
    issuer: str | None
    reference: str | None
    doc_type: str | None
    doc_date: date | None
    period_start: date | None
    period_end: date | None
    fiscal_year: int | None
    amount: float | None
    currency: Literal["EUR", "RON"] | None
    due_date: date | None
    addressee: str | None
    path: str
    filed_by: Literal["mona", "user"] | None
    filed_at: datetime | None
    rule: RuleRef | None
    confidence: int | None
    band: Literal["high", "medium", "low"] | None
    reasons: list[str]
    unverified_fields: list[str]
    deadline_ids: list[str]
    page_count: int | None


class Total(Strict):
    currency: Literal["EUR", "RON"]
    total: float


class Excluded(Strict):
    id: str
    reason: Literal["no_amount", "not_found", "other_currency"]


class SumResult(Carded):
    count: int
    totals: list[Total]
    document_ids: list[str] = Field(max_length=25)
    listed: int
    excluded: list[Excluded] = Field(max_length=10)


class Suggestion(Strict):
    entity: EntityRef | None
    category: CategoryRef | None
    confidence: int | None


class QueueItem(Strict):
    document_id: str = DocId
    title: str
    reasons: list[Literal["low", "entity", "conflict", "unreadable"]]
    suggestion: Suggestion
    arrived_at: datetime


class QueueResult(Carded):
    total: int
    next_cursor: str | None
    items: list[QueueItem]
    truncated: bool = False


class DeadlineItem(Strict):
    deadline_id: str
    document_id: str | None
    label: str
    entity: EntityRef
    due_date: date
    days_left: int
    amount: float | None
    currency: Literal["EUR", "RON"] | None
    status: Literal["open"]
    reminder_on: date | None


class DeadlinesResult(Carded):
    total: int
    next_cursor: str | None
    items: list[DeadlineItem]
    truncated: bool = False


class EntityCount(Strict):
    key: str
    name: str
    count: int


class Filed(Strict):
    count: int
    by_entity: list[EntityCount]


class NeedsReview(Strict):
    count: int
    by_reason: dict[Literal["low", "entity", "conflict", "unreadable"], int]


class DueSoon(Strict):
    deadline_id: str
    label: str
    entity: EntityRef
    due_date: date
    days_left: int
    amount: float | None
    currency: Literal["EUR", "RON"] | None


class ReminderToday(Strict):
    reminder_id: str
    label: str | None
    note: str | None


class Learned(Strict):
    rule_id: str
    name: str
    created_at: datetime
    fired_since: int


class PendingInterview(Strict):
    interview_id: str
    open_questions: int


class BriefResult(Strict):
    generated_at: datetime
    since: datetime
    filed: Filed
    needs_review: NeedsReview
    due_soon: list[DueSoon] = Field(max_length=5)
    reminders_today: list[ReminderToday]
    learned: list[Learned]
    pending_interview: PendingInterview | None
    truncated: bool = False


RESULT_MODELS: dict[str, type[BaseModel]] = {
    "search_documents": SearchResult,
    "get_document": DocumentResult,
    "sum_amounts": SumResult,
    "list_review_queue": QueueResult,
    "list_deadlines": DeadlinesResult,
    "get_brief": BriefResult,
}

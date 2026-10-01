"""ORM mapping of the C1 schema. Migration 0003 is the source of truth (CHECKs live there)."""

from datetime import date, datetime
from decimal import Decimal
from functools import partial
from typing import Any

from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    Boolean,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from mona.ids import new_id

NAMING = {
    "pk": "%(table_name)s_pkey",
    "uq": "%(table_name)s_%(column_0_N_name)s_key",
    "fk": "%(table_name)s_%(column_0_N_name)s_fkey",
}

EMPTY_ARRAY = text("'{}'::text[]")


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)
    type_annotation_map = {
        str: Text,
        int: Integer,
        bool: Boolean,
        datetime: TIMESTAMP(timezone=True),
        date: Date,
        Decimal: Numeric(14, 2),
        bytes: LargeBinary,
        dict[str, Any]: JSONB,
        list[Any]: JSONB,
        list[str]: ARRAY(Text),
    }


def _id(prefix: str) -> Mapped[str]:
    return mapped_column(primary_key=True, default=partial(new_id, prefix))


def _fk(target: str, ondelete: str | None = None, *, use_alter: bool = False, **kw: Any) -> Any:
    return mapped_column(ForeignKey(target, ondelete=ondelete, use_alter=use_alter), **kw)


def _created() -> Mapped[datetime]:
    return mapped_column(server_default=func.now())


def _updated() -> Mapped[datetime]:
    return mapped_column(server_default=func.now(), onupdate=func.now())


def _small(**kw: Any) -> Any:
    return mapped_column(SmallInteger, **kw)


def _strings() -> Mapped[list[str]]:
    return mapped_column(server_default=EMPTY_ARRAY)


# §2 Registry


class Entity(Base):
    __tablename__ = "entities"
    __table_args__ = (
        Index(
            "entities_one_visitors",
            text("(true)"),
            unique=True,
            postgresql_where=text("purge_after_hours IS NOT NULL"),
        ),
    )

    id: Mapped[str] = _id("ent")
    key: Mapped[str] = mapped_column(unique=True)
    display_name: Mapped[str]
    folder_name: Mapped[str] = mapped_column(unique=True)
    legal_form: Mapped[str | None]
    siren: Mapped[str | None]
    visibility: Mapped[str] = mapped_column(server_default="practice")
    fy_end_month: Mapped[int] = _small(server_default="12")
    fy_end_day: Mapped[int] = _small(server_default="31")
    filing_language: Mapped[str | None]
    aliases: Mapped[list[str]] = _strings()
    addresses: Mapped[list[str]] = _strings()
    purge_after_hours: Mapped[int | None]
    sort_order: Mapped[int] = mapped_column(server_default="0")
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()

    sub_units: Mapped[list["SubUnit"]] = relationship(
        back_populates="entity", lazy="selectin", order_by="SubUnit.key"
    )


class SubUnit(Base):
    __tablename__ = "sub_units"
    __table_args__ = (UniqueConstraint("entity_id", "key"), UniqueConstraint("entity_id", "label"))

    id: Mapped[str] = _id("sub")
    entity_id: Mapped[str] = _fk("entities.id", "RESTRICT")
    key: Mapped[str]
    label: Mapped[str]
    person_id: Mapped[str | None] = _fk("people.id", "SET NULL")
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()

    entity: Mapped[Entity] = relationship(back_populates="sub_units", lazy="raise")


class Person(Base):
    __tablename__ = "people"

    id: Mapped[str] = _id("per")
    key: Mapped[str] = mapped_column(unique=True)
    display_name: Mapped[str]
    short_name: Mapped[str | None]
    aliases: Mapped[list[str]] = _strings()
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class EntityPerson(Base):
    __tablename__ = "entity_people"

    entity_id: Mapped[str] = _fk("entities.id", "CASCADE", primary_key=True)
    person_id: Mapped[str] = _fk("people.id", "CASCADE", primary_key=True)
    role: Mapped[str | None]


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = _id("acc")
    key: Mapped[str] = mapped_column(unique=True)
    entity_id: Mapped[str] = _fk("entities.id", "RESTRICT")
    sub_unit_id: Mapped[str | None] = _fk("sub_units.id", "SET NULL")
    bank_counterparty_id: Mapped[str | None] = _fk("counterparties.id", "SET NULL")
    label: Mapped[str]
    iban_hash: Mapped[str] = mapped_column(unique=True)
    iban_last4: Mapped[str]
    currency: Mapped[str] = mapped_column(server_default="EUR")
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class Counterparty(Base):
    __tablename__ = "counterparties"
    __table_args__ = (
        Index(
            "counterparties_name_trgm",
            "name_norm",
            postgresql_using="gin",
            postgresql_ops={"name_norm": "gin_trgm_ops"},
        ),
    )

    id: Mapped[str] = _id("cpt")
    key: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str]
    name_norm: Mapped[str] = mapped_column(unique=True)
    kind: Mapped[str | None]
    siren: Mapped[str | None]
    origin: Mapped[str]
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()

    aliases: Mapped[list["CounterpartyAlias"]] = relationship(
        lazy="selectin", order_by="CounterpartyAlias.alias_norm"
    )


class CounterpartyAlias(Base):
    __tablename__ = "counterparty_aliases"

    alias_norm: Mapped[str] = mapped_column(primary_key=True)
    counterparty_id: Mapped[str] = _fk("counterparties.id", "CASCADE")


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[str] = mapped_column(primary_key=True)
    labels: Mapped[dict[str, Any]]
    icon: Mapped[str] = mapped_column(server_default="invoice")
    model_definition: Mapped[str]
    sort_order: Mapped[int] = mapped_column(server_default="0")
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()

    subcategories: Mapped[list["Subcategory"]] = relationship(
        lazy="selectin", order_by="Subcategory.sort_order"
    )


class Subcategory(Base):
    __tablename__ = "subcategories"

    category_id: Mapped[str] = _fk("categories.id", "CASCADE", primary_key=True)
    key: Mapped[str] = mapped_column(primary_key=True)
    labels: Mapped[dict[str, Any]]
    sort_order: Mapped[int] = mapped_column(server_default="0")


class Template(Base):
    __tablename__ = "templates"
    __table_args__ = (
        UniqueConstraint("category_id", "entity_id", postgresql_nulls_not_distinct=True),
    )

    id: Mapped[str] = _id("tpl")
    category_id: Mapped[str] = _fk("categories.id", "CASCADE")
    entity_id: Mapped[str | None] = _fk("entities.id", "CASCADE")
    path_template: Mapped[str]
    file_template: Mapped[str]
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


# §3 Rules


class Rule(Base):
    __tablename__ = "rules"
    __table_args__ = (
        Index("rules_active", text("priority DESC"), postgresql_where=text("state = 'active'")),
    )

    id: Mapped[str] = _id("rul")
    key: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str]
    state: Mapped[str] = mapped_column(server_default="active")
    source: Mapped[str]
    priority: Mapped[int]
    conditions: Mapped[list[Any]]
    action: Mapped[dict[str, Any]]
    condition_text: Mapped[dict[str, Any]]
    version: Mapped[int] = mapped_column(server_default="1")
    fired_count: Mapped[int] = mapped_column(server_default="0")
    last_fired_at: Mapped[datetime | None]
    corrections_since: Mapped[int] = mapped_column(server_default="0")
    origin_question_id: Mapped[str | None] = _fk(
        "interview_questions.id", "SET NULL", use_alter=True
    )
    origin_document_id: Mapped[str | None] = _fk("documents.id", "SET NULL", use_alter=True)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class RuleVersion(Base):
    __tablename__ = "rule_versions"

    rule_id: Mapped[str] = _fk("rules.id", "CASCADE", primary_key=True)
    version: Mapped[int] = mapped_column(primary_key=True)
    conditions: Mapped[list[Any]]
    action: Mapped[dict[str, Any]]
    condition_text: Mapped[dict[str, Any]]
    priority: Mapped[int]
    created_at: Mapped[datetime] = _created()


# §4 Documents


class Batch(Base):
    __tablename__ = "batches"

    id: Mapped[str] = _id("bat")
    source: Mapped[str]
    status: Mapped[str] = mapped_column(server_default="running")
    title: Mapped[str | None]
    visitor: Mapped[bool] = mapped_column(server_default=text("false"))
    started_at: Mapped[datetime] = _created()
    finished_at: Mapped[datetime | None]
    debrief_interview_id: Mapped[str | None] = _fk("interviews.id", "SET NULL", use_alter=True)
    created_at: Mapped[datetime] = _created()


class IntakeItem(Base):
    __tablename__ = "intake_items"

    id: Mapped[str] = _id("itm")
    batch_id: Mapped[str] = _fk("batches.id", "CASCADE")
    original_name: Mapped[str]
    sha256: Mapped[str]
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    outcome: Mapped[str]
    document_id: Mapped[str | None] = _fk("documents.id", "SET NULL")
    reject_reason: Mapped[str | None]
    created_at: Mapped[datetime] = _created()


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["category_id", "subcategory_key"],
            ["subcategories.category_id", "subcategories.key"],
            ondelete="SET NULL (subcategory_key)",
        ),
        UniqueConstraint("location", "current_path"),
        Index("documents_fts", "fts", postgresql_using="gin"),
        Index(
            "documents_head",
            "head_norm",
            postgresql_using="gin",
            postgresql_ops={"head_norm": "gin_trgm_ops"},
        ),
        Index(
            "documents_facets",
            "entity_id",
            "category_id",
            "fiscal_year",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "documents_status",
            "status",
            text("arrived_at DESC"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("documents_cpt", "counterparty_id", postgresql_where=text("deleted_at IS NULL")),
        Index("documents_doc_date", "doc_date", postgresql_where=text("deleted_at IS NULL")),
        Index(
            "documents_sha256_live",
            "sha256",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[str] = _id("doc")
    sha256: Mapped[str]
    original_name: Mapped[str]
    mime_type: Mapped[str]
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    page_count: Mapped[int | None]
    source: Mapped[str]
    batch_id: Mapped[str] = _fk("batches.id", "RESTRICT")
    arrived_at: Mapped[datetime] = _created()

    location: Mapped[str]
    current_path: Mapped[str]
    status: Mapped[str]
    pipeline_stage: Mapped[str] = mapped_column(server_default="queued")
    pipeline_error: Mapped[str | None]
    reasons: Mapped[list[str]] = _strings()

    title: Mapped[str | None]
    entity_id: Mapped[str | None] = _fk("entities.id", "RESTRICT")
    sub_unit_id: Mapped[str | None] = _fk("sub_units.id", "SET NULL")
    category_id: Mapped[str | None] = _fk("categories.id", "RESTRICT")
    subcategory_key: Mapped[str | None]
    counterparty_id: Mapped[str | None] = _fk("counterparties.id", "SET NULL")
    issuer: Mapped[str | None]
    reference: Mapped[str | None]
    doc_type: Mapped[str | None]
    doc_date: Mapped[date | None]
    period_start: Mapped[date | None]
    period_end: Mapped[date | None]
    fiscal_year: Mapped[int | None]
    amount: Mapped[Decimal | None]
    currency: Mapped[str | None]
    due_date: Mapped[date | None]
    addressee: Mapped[str | None]
    addressee_person_id: Mapped[str | None] = _fk("people.id", "SET NULL")
    confidence: Mapped[int | None] = _small()
    band: Mapped[str | None]

    extraction_id: Mapped[str | None] = _fk("extractions.id", "SET NULL", use_alter=True)
    classification_id: Mapped[str | None] = _fk("classifications.id", "SET NULL", use_alter=True)
    rule_id: Mapped[str | None] = _fk("rules.id", "SET NULL")
    filed_at: Mapped[datetime | None]
    filed_by: Mapped[str | None]
    filed_op_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("file_ops.id", use_alter=True)
    )
    deleted_at: Mapped[datetime | None]

    head_norm: Mapped[str | None]
    fts: Mapped[Any | None] = mapped_column(TSVECTOR)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class Extraction(Base):
    __tablename__ = "extractions"
    __table_args__ = (UniqueConstraint("document_id", "version"),)

    id: Mapped[str] = _id("ext")
    document_id: Mapped[str] = _fk("documents.id", "CASCADE")
    version: Mapped[int]
    text_method: Mapped[str]
    text_cache_key: Mapped[str]
    char_count: Mapped[int]
    model: Mapped[str | None]
    prompt_version: Mapped[str | None]
    raw_output: Mapped[dict[str, Any] | None]
    from_cache: Mapped[bool] = mapped_column(server_default=text("false"))
    duration_ms: Mapped[int | None]
    prompt_tokens: Mapped[int | None]
    completion_tokens: Mapped[int | None]
    created_at: Mapped[datetime] = _created()

    fields: Mapped[list["ExtractionField"]] = relationship(lazy="selectin")


class ExtractionField(Base):
    __tablename__ = "extraction_fields"

    extraction_id: Mapped[str] = _fk("extractions.id", "CASCADE", primary_key=True)
    key: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[str]
    currency: Mapped[str | None]
    quote: Mapped[str]
    page: Mapped[int]
    stated_page: Mapped[int]
    verified: Mapped[bool]
    find_query: Mapped[str | None]
    confidence: Mapped[int] = _small()


class Classification(Base):
    __tablename__ = "classifications"
    __table_args__ = (Index("classifications_doc", "document_id", text("created_at DESC")),)

    id: Mapped[str] = _id("cls")
    document_id: Mapped[str] = _fk("documents.id", "CASCADE")
    extraction_id: Mapped[str | None] = _fk("extractions.id", "SET NULL")
    method: Mapped[str]
    rule_id: Mapped[str | None] = _fk("rules.id", "SET NULL")
    conflicting_rule_ids: Mapped[list[str]] = _strings()
    entity_id: Mapped[str | None] = _fk("entities.id")
    sub_unit_id: Mapped[str | None] = _fk("sub_units.id")
    category_id: Mapped[str | None] = _fk("categories.id")
    subcategory_key: Mapped[str | None]
    counterparty_id: Mapped[str | None] = _fk("counterparties.id")
    model_confidence: Mapped[int | None] = _small()
    confidence: Mapped[int] = _small()
    band: Mapped[str]
    reasons: Mapped[list[str]] = _strings()
    proposed_path: Mapped[str | None]
    proposed_file_name: Mapped[str | None]
    created_at: Mapped[datetime] = _created()


class ReviewItem(Base):
    __tablename__ = "review_items"
    __table_args__ = (
        Index(
            "review_items_one_open",
            "document_id",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
    )

    id: Mapped[str] = _id("rev")
    document_id: Mapped[str] = _fk("documents.id", "CASCADE")
    reasons: Mapped[list[str]]
    status: Mapped[str] = mapped_column(server_default="open")
    resolution: Mapped[str | None]
    scope: Mapped[str | None]
    rule_id: Mapped[str | None] = _fk("rules.id", "SET NULL")
    resolved_by: Mapped[str | None]
    created_at: Mapped[datetime] = _created()
    resolved_at: Mapped[datetime | None]


# §5 Journal


class OpGroup(Base):
    __tablename__ = "op_groups"
    __table_args__ = (
        Index(
            "op_groups_intake",
            "batch_id",
            unique=True,
            postgresql_where=text("kind = 'intake_batch'"),
        ),
    )

    id: Mapped[str] = _id("grp")
    kind: Mapped[str]
    actor: Mapped[str]
    via: Mapped[str]
    batch_id: Mapped[str | None] = _fk("batches.id", "SET NULL")
    rule_id: Mapped[str | None] = _fk("rules.id", "SET NULL")
    target_group_id: Mapped[str | None] = _fk("op_groups.id")
    created_at: Mapped[datetime] = _created()


class FileOp(Base):
    __tablename__ = "file_ops"
    __table_args__ = (
        Index("file_ops_doc", "document_id", text("id DESC")),
        Index("file_ops_group", "group_id", text("id DESC")),
        Index("file_ops_pending", "id", postgresql_where=text("fs_state = 'pending'")),
        Index(
            "file_ops_undo_of_live",
            "undo_of",
            unique=True,
            postgresql_where=text("fs_state <> 'failed'"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    at: Mapped[datetime] = _created()
    actor: Mapped[str]
    via: Mapped[str]
    action: Mapped[str]
    document_id: Mapped[str | None] = _fk("documents.id", "RESTRICT")
    subject_id: Mapped[str | None]
    sha256: Mapped[str | None]
    before: Mapped[dict[str, Any] | None]
    after: Mapped[dict[str, Any] | None]
    fs_state: Mapped[str] = mapped_column(server_default="done")
    batch_id: Mapped[str | None] = _fk("batches.id", "SET NULL")
    group_id: Mapped[str | None] = _fk("op_groups.id", "SET NULL")
    rule_id: Mapped[str | None] = _fk("rules.id", "SET NULL")
    confidence: Mapped[int | None] = _small()
    band: Mapped[str | None]
    undoable: Mapped[bool]
    undone_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("file_ops.id"), unique=True
    )
    undo_of: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("file_ops.id"))


# §6 Workflow


class Interview(Base):
    __tablename__ = "interviews"

    id: Mapped[str] = _id("int")
    kind: Mapped[str]
    status: Mapped[str] = mapped_column(server_default="generating")
    scope: Mapped[dict[str, Any]]
    lang: Mapped[str]
    batch_id: Mapped[str | None] = _fk("batches.id", "SET NULL")
    conversation_id: Mapped[str | None] = _fk("conversations.id", "SET NULL")
    analysis: Mapped[str | None]
    error: Mapped[str | None]
    created_at: Mapped[datetime] = _created()
    ready_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]

    questions: Mapped[list["InterviewQuestion"]] = relationship(
        lazy="selectin", order_by="InterviewQuestion.ordinal"
    )


class InterviewQuestion(Base):
    __tablename__ = "interview_questions"
    __table_args__ = (UniqueConstraint("interview_id", "ordinal"),)

    id: Mapped[str] = _id("qst")
    interview_id: Mapped[str] = _fk("interviews.id", "CASCADE")
    ordinal: Mapped[int] = _small()
    text: Mapped[str]
    impact: Mapped[int]
    affected_document_ids: Mapped[list[str]]
    evidence: Mapped[list[Any]]
    options: Mapped[list[Any]]
    suggestion_confidence: Mapped[int] = _small()
    status: Mapped[str] = mapped_column(server_default="open")
    created_at: Mapped[datetime] = _created()


class InterviewAnswer(Base):
    __tablename__ = "interview_answers"

    id: Mapped[str] = _id("ans")
    question_id: Mapped[str] = _fk("interview_questions.id", "CASCADE", unique=True)
    option_id: Mapped[str | None]
    free_text: Mapped[str | None]
    actor: Mapped[str]
    via: Mapped[str]
    created_at: Mapped[datetime] = _created()


class Deadline(Base):
    __tablename__ = "deadlines"
    __table_args__ = (
        Index(
            "deadlines_doc_date",
            "document_id",
            "due_date",
            unique=True,
            postgresql_where=text("document_id IS NOT NULL"),
        ),
    )

    id: Mapped[str] = _id("ddl")
    document_id: Mapped[str | None] = _fk("documents.id", "SET NULL")
    entity_id: Mapped[str] = _fk("entities.id", "RESTRICT")
    label: Mapped[str]
    due_date: Mapped[date]
    amount: Mapped[Decimal | None]
    currency: Mapped[str | None]
    paid_by_account_id: Mapped[str | None] = _fk("accounts.id", "SET NULL")
    status: Mapped[str] = mapped_column(server_default="open")
    origin: Mapped[str]
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class Reminder(Base):
    __tablename__ = "reminders"
    __table_args__ = (
        Index(
            "reminders_once",
            text("coalesce(deadline_id, document_id)"),
            "remind_on",
            unique=True,
            postgresql_where=text("status = 'scheduled'"),
        ),
    )

    id: Mapped[str] = _id("rem")
    deadline_id: Mapped[str | None] = _fk("deadlines.id", "CASCADE")
    document_id: Mapped[str | None] = _fk("documents.id", "CASCADE")
    remind_on: Mapped[date]
    note: Mapped[str | None]
    status: Mapped[str] = mapped_column(server_default="scheduled")
    created_by: Mapped[str]
    created_at: Mapped[datetime] = _created()
    delivered_at: Mapped[datetime | None]


class Draft(Base):
    __tablename__ = "drafts"

    id: Mapped[str] = _id("drf")
    document_id: Mapped[str] = _fk("documents.id", "CASCADE")
    lang: Mapped[str]
    instructions: Mapped[str | None]
    status: Mapped[str] = mapped_column(server_default="generating")
    title: Mapped[str | None]
    body: Mapped[str | None]
    error: Mapped[str | None]
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class Export(Base):
    __tablename__ = "exports"

    id: Mapped[str] = _id("exp")
    entity_id: Mapped[str] = _fk("entities.id", "RESTRICT")
    fiscal_year: Mapped[int]
    status: Mapped[str] = mapped_column(server_default="building")
    document_count: Mapped[int | None]
    zip_path: Mapped[str | None]
    csv_path: Mapped[str | None]
    error: Mapped[str | None]
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


# §7 Chat


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = _id("cnv")
    title: Mapped[str]
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()
    last_message_at: Mapped[datetime] = _created()


class ChatTurn(Base):
    __tablename__ = "chat_turns"
    __table_args__ = (
        Index(
            "chat_turns_one_open",
            "conversation_id",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
        Index("chat_turns_conv", "conversation_id", "opened_at"),
    )

    id: Mapped[str] = _id("trn")
    conversation_id: Mapped[str] = _fk("conversations.id", "CASCADE")
    status: Mapped[str] = mapped_column(server_default="open")
    user_text: Mapped[str]
    ui_message_id: Mapped[str]
    reply_language: Mapped[str]
    opened_at: Mapped[datetime] = _created()
    lease_expires_at: Mapped[datetime]
    closed_at: Mapped[datetime | None]
    reasoning_ms: Mapped[int | None]
    finish_reason: Mapped[str | None]
    error_code: Mapped[str | None]
    usage: Mapped[dict[str, Any] | None]
    parts: Mapped[list[Any]] = mapped_column(server_default=text("'[]'::jsonb"))


class CardEvent(Base):
    __tablename__ = "card_events"
    __table_args__ = (Index("card_events_turn", "turn_id", "created_at"),)

    id: Mapped[str] = _id("crd")
    tool: Mapped[str]
    kind: Mapped[str]
    subject: Mapped[dict[str, Any]]
    channel: Mapped[str]
    turn_id: Mapped[str | None] = _fk("chat_turns.id", "SET NULL")
    emitted_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = _created()


class CardActionNote(Base):
    __tablename__ = "card_action_notes"
    __table_args__ = (
        Index(
            "card_action_notes_pending",
            "conversation_id",
            "created_at",
            postgresql_where=text("consumed_turn_id IS NULL"),
        ),
    )

    id: Mapped[str] = _id("not")
    conversation_id: Mapped[str] = _fk("conversations.id", "CASCADE")
    kind: Mapped[str]
    text: Mapped[str]
    created_at: Mapped[datetime] = _created()
    consumed_turn_id: Mapped[str | None] = _fk("chat_turns.id", "SET NULL")


# §8 Profile and settings


class Profile(Base):
    __tablename__ = "profile"

    singleton: Mapped[bool] = mapped_column(primary_key=True, server_default=text("true"))
    name: Mapped[str]
    password_hash: Mapped[str]
    locale: Mapped[str] = mapped_column(server_default="en")
    auto_lock_minutes: Mapped[int] = mapped_column(server_default="15")
    locked_at: Mapped[datetime | None]
    password_changed_at: Mapped[datetime] = _created()
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class PracticeSettings(Base):
    __tablename__ = "settings"

    singleton: Mapped[bool] = mapped_column(primary_key=True, server_default=text("true"))
    practice_name: Mapped[str]
    filing_language: Mapped[str] = mapped_column(server_default="fr")
    confidence_high: Mapped[int] = _small(server_default="90")
    confidence_low: Mapped[int] = _small(server_default="75")
    badge_hours: Mapped[int] = _small(server_default="24")
    debrief_queue_threshold: Mapped[int] = _small(server_default="5")
    debrief_early_min: Mapped[int] = _small(server_default="5")
    iban_salt: Mapped[bytes]
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        Index("auth_sessions_live", "expires_at", postgresql_where=text("revoked_at IS NULL")),
    )

    id: Mapped[str] = _id("ses")
    token_hash: Mapped[str] = mapped_column(unique=True)
    created_at: Mapped[datetime] = _created()
    expires_at: Mapped[datetime]
    last_active_at: Mapped[datetime] = _created()
    revoked_at: Mapped[datetime | None]
    user_agent: Mapped[str | None]
    updated_at: Mapped[datetime] = _updated()

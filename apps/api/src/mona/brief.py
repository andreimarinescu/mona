"""The brief's facts (C4 §3.15, C2 §3.2 `BriefFacts`), shared by `get_brief` and Home."""

from collections.abc import Collection
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import and_, any_, exists, func, or_, select
from sqlalchemy.orm import aliased

from mona.db.models import (
    Deadline,
    Document,
    Entity,
    FileOp,
    Interview,
    InterviewQuestion,
    Reminder,
    Rule,
)
from mona.visibility import Scope, rule_visibility

DUE_DAYS, DUE_MAX, LEARNED_MAX = 7, 5, 10


@dataclass
class Facts:
    generated_at: datetime
    since: datetime
    today: date
    filed: list[Any] = field(default_factory=list)  # (entity_id, key, name, count)
    review_reasons: list[list[str]] = field(default_factory=list)
    due: list[Any] = field(default_factory=list)
    reminders: list[Any] = field(default_factory=list)
    learned: list[Any] = field(default_factory=list)
    pending: Any = None

    @property
    def by_reason(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for reasons in self.review_reasons:
            for reason in reasons:
                out[reason] = out.get(reason, 0) + 1
        return out


def deadline_query(scope: Scope, *clauses: Any, statuses: Collection[str] = ("open",)) -> Any:
    """Deadlines in `statuses`, visible on the channel and outside the Visitors figures."""
    return (
        select(
            Deadline.id,
            Deadline.document_id,
            Deadline.label,
            Deadline.due_date,
            Deadline.amount,
            Deadline.currency,
            Deadline.status,
            Deadline.entity_id,
            Entity.key.label("entity_key"),
            Entity.display_name.label("entity_name"),
        )
        .join(Entity, Entity.id == Deadline.entity_id)
        .outerjoin(Document, Document.id == Deadline.document_id)
        .where(Deadline.status.in_(list(statuses)), *scope.deadline_clauses(), *clauses)
    )


async def facts(
    scope: Scope, *, since: datetime, now: datetime, today: date, entity_id: str | None = None
) -> Facts:
    conn = scope.conn
    out = Facts(generated_at=now, since=since, today=today)
    doc_clauses = [*scope.document_clauses(), *scope.figures_clauses()]
    if entity_id is not None:
        doc_clauses.append(Document.entity_id == entity_id)
    out.filed = (
        await conn.execute(
            select(Entity.id, Entity.key, Entity.display_name, func.count(Document.id))
            .select_from(Document)
            .join(Entity, Entity.id == Document.entity_id)
            .where(
                Document.status == "filed",
                Document.filed_at >= since,
                Document.filed_at <= now,
                *doc_clauses,
            )
            .group_by(Entity.id, Entity.key, Entity.display_name, Entity.sort_order)
            .order_by(func.count(Document.id).desc(), Entity.sort_order)
        )
    ).all()
    out.review_reasons = [
        list(r)
        for r in (
            await conn.execute(
                select(Document.reasons).where(
                    Document.status.in_(("review", "unreadable")), *doc_clauses
                )
            )
        ).scalars()
    ]
    due = [Deadline.due_date <= today + timedelta(days=DUE_DAYS)]
    if entity_id is not None:
        due.append(Deadline.entity_id == entity_id)
    out.due = (
        await conn.execute(
            deadline_query(scope, *due).order_by(Deadline.due_date, Deadline.id).limit(DUE_MAX)
        )
    ).all()
    out.reminders = await _reminders(scope, today, entity_id)
    out.learned = await _learned(scope, since)
    out.pending = await _pending(scope)
    return out


async def _reminders(scope: Scope, today: date, entity_id: str | None) -> list[Any]:
    doc = aliased(Document)
    visible_doc = or_(
        doc.id.is_(None), and_(*scope.document_clauses(doc), *scope.figures_clauses(doc))
    )
    visible_deadline = or_(Deadline.id.is_(None), and_(*scope.deadline_clauses(Document)))
    clauses = [
        Reminder.status == "scheduled",
        Reminder.remind_on == today,
        visible_doc,
        visible_deadline,
    ]
    if entity_id is not None:
        clauses.append(func.coalesce(Deadline.entity_id, doc.entity_id) == entity_id)
    return (
        await scope.conn.execute(
            select(
                Reminder.id,
                Reminder.note,
                func.coalesce(Deadline.label, doc.title, doc.original_name).label("label"),
            )
            .outerjoin(Deadline, Deadline.id == Reminder.deadline_id)
            .outerjoin(Document, Document.id == Deadline.document_id)
            .outerjoin(doc, doc.id == func.coalesce(Reminder.document_id, Deadline.document_id))
            .where(*clauses)
            .order_by(Reminder.created_at, Reminder.id)
        )
    ).all()


async def _learned(scope: Scope, since: datetime) -> list[Any]:
    fired = (
        select(func.count(func.distinct(FileOp.document_id)))
        .where(FileOp.rule_id == Rule.id, FileOp.at >= since, FileOp.fs_state == "done")
        .scalar_subquery()
    )
    rows = (
        await scope.conn.execute(
            select(
                Rule.id, Rule.name, Rule.created_at, Rule.conditions, Rule.action,
                fired.label("fired"),
            )
            .where(Rule.source != "seed", Rule.state == "active", Rule.created_at >= since)
            .order_by(Rule.created_at, Rule.id)
        )
    ).all()  # fmt: skip
    seen = await rule_visibility(scope)
    return [r for r in rows if seen is None or seen.visible(r.conditions, r.action)][:LEARNED_MAX]


async def _pending(scope: Scope) -> Any:
    counted = [InterviewQuestion.interview_id == Interview.id, InterviewQuestion.status == "open"]
    if scope.channel == "telegram":
        counted.append(
            exists().where(
                Document.id == any_(InterviewQuestion.affected_document_ids),
                *scope.document_clauses(),
                *scope.figures_clauses(),
            )
        )
    open_questions = select(func.count(InterviewQuestion.id)).where(*counted).scalar_subquery()
    return (
        await scope.conn.execute(
            select(Interview.id, open_questions.label("n"))
            .where(Interview.status == "ready", open_questions > 0)
            .order_by(Interview.created_at.desc(), Interview.id.desc())
            .limit(1)
        )
    ).first()

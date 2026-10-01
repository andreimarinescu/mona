"""C1 §11 DTOs built from current DB state (card payloads, C3 §5.5; C2 serves the same)."""

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection

from mona import clock
from mona.db.models import (
    Account,
    Counterparty,
    Deadline,
    Document,
    Draft,
    Entity,
    Export,
    Interview,
    InterviewAnswer,
    InterviewQuestion,
    PracticeSettings,
    Reminder,
    Rule,
)
from mona.dto import models as dto
from mona.settings import get_settings

logger = logging.getLogger(__name__)

SUBJECT_KEYS = {
    "doc": "document_id",
    "deadline": "deadline_id",
    "interview": "interview_id",
    "rulePreview": "rule_id",
    "draft": "draft_id",
    "export": "export_id",
}


def _money(amount: Any, currency: str | None) -> dto.Money | None:
    return dto.Money(value=amount, currency=currency) if amount is not None and currency else None


def _thumbnail_url(document_id: str, sha256: str) -> str | None:
    cache = get_settings().mona_data_dir / "textcache" / sha256[:2] / f"{sha256}.p1.png"
    return f"/api/documents/{document_id}/thumbnail" if cache.is_file() else None


async def _badge_hours(conn: AsyncConnection) -> int:
    hours = (await conn.execute(select(PracticeSettings.badge_hours))).scalar()
    return hours or 24


def _badge_until(row: Any, hours: int, now: datetime) -> datetime | None:
    if row.status != "filed" or row.filed_by != "mona" or row.filed_at is None:
        return None
    until = row.filed_at + timedelta(hours=hours)
    return until if now < until else None


async def document_summaries(
    conn: AsyncConnection, ids: list[str]
) -> dict[str, dto.DocumentSummary]:
    """Non-deleted documents by id; missing or deleted ids are absent."""
    if not ids:
        return {}
    rows = (
        await conn.execute(
            select(
                Document,
                Entity.display_name.label("entity_name"),
                Counterparty.name.label("counterparty_name"),
                Rule.name.label("rule_name"),
            )
            .outerjoin(Entity, Entity.id == Document.entity_id)
            .outerjoin(Counterparty, Counterparty.id == Document.counterparty_id)
            .outerjoin(Rule, Rule.id == Document.rule_id)
            .where(Document.id.in_(ids), Document.deleted_at.is_(None))
        )
    ).all()
    hours, now = await _badge_hours(conn), clock.now()
    out = {}
    for r in rows:
        segments = r.current_path.split("/")
        out[r.id] = dto.DocumentSummary(
            id=r.id,
            title=r.title or r.original_name,
            original_name=r.original_name,
            file_name=segments[-1],
            path=segments[:-1] if r.location == "archive" else [],
            location=r.location,
            entity_id=r.entity_id,
            entity_name=r.entity_name,
            sub_unit_id=r.sub_unit_id,
            category_id=r.category_id,
            subcategory_key=r.subcategory_key,
            counterparty_id=r.counterparty_id,
            counterparty=r.counterparty_name,
            doc_type=r.doc_type,
            reference=r.reference,
            date=r.doc_date,
            period_start=r.period_start,
            period_end=r.period_end,
            fiscal_year=r.fiscal_year,
            amount=_money(r.amount, r.currency),
            due_date=r.due_date,
            status=r.status,
            reasons=list(r.reasons),
            confidence=r.confidence,
            band=r.band,
            pipeline_stage=r.pipeline_stage,
            arrived_at=r.arrived_at,
            source=r.source,
            filed_at=r.filed_at,
            filed_by=r.filed_by,
            badge_until=_badge_until(r, hours, now),
            rule={"id": r.rule_id, "name": r.rule_name} if r.rule_id else None,
            batch_id=r.batch_id,
            page_count=r.page_count,
            thumbnail_url=_thumbnail_url(r.id, r.sha256),
            pdf_url=f"/api/documents/{r.id}/pdf",
        )
    return out


async def deadlines(conn: AsyncConnection, ids: list[str]) -> dict[str, dto.Deadline]:
    """Deadlines by id, except those of a deleted document (C7 §7.4)."""
    if not ids:
        return {}
    rows = (
        await conn.execute(
            select(
                Deadline,
                Entity.display_name.label("entity_name"),
                Account.label.label("account_label"),
                Account.iban_last4,
            )
            .join(Entity, Entity.id == Deadline.entity_id)
            .outerjoin(Account, Account.id == Deadline.paid_by_account_id)
            .outerjoin(Document, Document.id == Deadline.document_id)
            .where(Deadline.id.in_(ids), Document.deleted_at.is_(None))
        )
    ).all()
    reminders = await next_reminders(conn, [r.id for r in rows])
    today = clock.paris_today()
    return {
        r.id: dto.Deadline(
            id=r.id,
            document_id=r.document_id,
            label=r.label,
            entity_id=r.entity_id,
            entity_name=r.entity_name,
            due_date=r.due_date,
            amount=_money(r.amount, r.currency),
            paid_by=f"{r.account_label} •• {r.iban_last4}" if r.account_label else None,
            status=r.status,
            days_left=(r.due_date - today).days,
            reminder=(
                {"id": reminders[r.id].id, "remind_on": reminders[r.id].remind_on}
                if r.id in reminders
                else None
            ),
        )
        for r in rows
    }


async def next_reminders(conn: AsyncConnection, deadline_ids: list[str]) -> dict[str, Any]:
    """The earliest scheduled reminder of each deadline."""
    if not deadline_ids:
        return {}
    rows = (
        await conn.execute(
            select(Reminder.id, Reminder.deadline_id, Reminder.remind_on)
            .where(Reminder.deadline_id.in_(deadline_ids), Reminder.status == "scheduled")
            .order_by(Reminder.remind_on.desc())
        )
    ).all()
    return {r.deadline_id: r for r in rows}


def interview_scope(scope: dict[str, Any]) -> dict[str, Any]:
    """C6 §2.1: the DTO form is the camelCase scope without the candidate snapshot."""
    kind = scope.get("type", "queue")
    keys = {"batch": "batch_id", "counterparty": "counterparty_id", "documents": "document_ids"}
    out: dict[str, Any] = {"type": kind}
    if kind in keys:
        out[keys[kind]] = scope[keys[kind]]
    return out


async def interview(conn: AsyncConnection, interview_id: str) -> dto.Interview | None:
    iv = (await conn.execute(select(Interview).where(Interview.id == interview_id))).first()
    if iv is None:
        return None
    qs = (
        await conn.execute(
            select(InterviewQuestion)
            .where(InterviewQuestion.interview_id == interview_id)
            .order_by(InterviewQuestion.ordinal)
        )
    ).all()
    questions: list[dto.InterviewQuestion] = []
    if iv.status != "generating":
        qids = [q.id for q in qs]
        answers = {
            a.question_id: a
            for a in await conn.execute(
                select(InterviewAnswer).where(InterviewAnswer.question_id.in_(qids))
            )
        }
        rule_ids: dict[str, list[str]] = {}
        for rid, qid in (
            await conn.execute(
                select(Rule.id, Rule.origin_question_id)
                .where(Rule.origin_question_id.in_(qids))
                .order_by(Rule.created_at, Rule.id)
            )
        ).all():
            rule_ids.setdefault(qid, []).append(rid)
        doc_ids = {e["document_id"] for q in qs for e in q.evidence}
        doc_ids |= {d for q in qs for d in q.affected_document_ids}
        docs = {
            r.id: r
            for r in await conn.execute(
                select(
                    Document.id, Document.title, Document.original_name, Document.deleted_at
                ).where(Document.id.in_(doc_ids))
            )
        }
        for q in qs:
            a = answers.get(q.id)
            affects = [
                d for d in q.affected_document_ids if d in docs and docs[d].deleted_at is None
            ]
            questions.append(
                dto.InterviewQuestion(
                    id=q.id,
                    ordinal=q.ordinal,
                    question=q.text,
                    lang=iv.lang,
                    affects=affects,
                    affects_count=len(affects),
                    evidence=[
                        {
                            **e,
                            "document_title": (
                                docs[e["document_id"]].title or docs[e["document_id"]].original_name
                                if e["document_id"] in docs
                                else ""
                            ),
                        }
                        for e in q.evidence
                    ],
                    options=q.options,
                    suggestion_confidence=q.suggestion_confidence,
                    status=q.status,
                    answer=(
                        {
                            "option_id": a.option_id,
                            "free_text": a.free_text,
                            "rule_ids": rule_ids.get(q.id, []),
                        }
                        if a
                        else None
                    ),
                )
            )
    source = None
    if qs:
        source = "cache" if iv.analysis is None else "live"
    return dto.Interview(
        id=iv.id,
        kind=iv.kind,
        status=iv.status,
        questions=questions,
        batch_id=iv.batch_id,
        created_at=iv.created_at,
        lang=iv.lang,
        scope=interview_scope(iv.scope),
        open_questions=sum(1 for q in qs if q.status == "open"),
        ready_at=iv.ready_at,
        finished_at=iv.finished_at,
        error=iv.error,
        source=source,
    )


async def draft(conn: AsyncConnection, draft_id: str) -> dto.Draft | None:
    d = (await conn.execute(select(Draft).where(Draft.id == draft_id))).first()
    if d is None:
        return None
    return dto.Draft(
        id=d.id,
        document_id=d.document_id,
        lang=d.lang,
        status=d.status,
        title=d.title,
        body=d.body,
        docx_url=f"/api/drafts/{d.id}/docx" if d.status == "ready" else None,
    )


async def export(conn: AsyncConnection, export_id: str) -> dto.ExportPack | None:
    e = (
        await conn.execute(
            select(Export, Entity.display_name)
            .join(Entity, Entity.id == Export.entity_id)
            .where(Export.id == export_id)
        )
    ).first()
    if e is None:
        return None
    ready = e.status == "ready"
    return dto.ExportPack(
        id=e.id,
        entity_id=e.entity_id,
        entity_name=e.display_name,
        fiscal_year=e.fiscal_year,
        status=e.status,
        document_count=e.document_count,
        zip_url=f"/api/exports/{e.id}/zip" if ready and e.zip_path else None,
        csv_url=f"/api/exports/{e.id}/csv" if ready and e.csv_path else None,
    )


async def card_payload(conn: AsyncConnection, kind: str, subject_id: str) -> dict | None:
    """The `data` of a `data-<kind>` part, or None when its subject is gone (C3 §5.5)."""
    found: Any
    if kind == "doc":
        found = (await document_summaries(conn, [subject_id])).get(subject_id)
    elif kind == "deadline":
        found = (await deadlines(conn, [subject_id])).get(subject_id)
    elif kind == "interview":
        found = await interview(conn, subject_id)
    elif kind == "draft":
        found = await draft(conn, subject_id)
    elif kind == "export":
        found = await export(conn, subject_id)
    else:
        logger.warning("card kind %s has no payload builder yet", kind)
        return None
    return found.model_dump(mode="json") if found is not None else None

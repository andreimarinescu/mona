"""C6 §2.3, §3.5, §8: start or reuse an interview, cancel it, and the stale-job sweep."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Connection, func, select, text, update

from mona.db.models import Base
from mona.interviews.candidates import (
    candidates,
    reusable_clause,
    scope_equal,
    scope_filter,
    seed_candidates,
    snapshot,
)
from mona.interviews.config import STALE_AFTER
from mona.interviews.triggers import create
from mona.services import Ctx, ServiceError
from mona.workflow.common import attributed_turn, profile_locale, write_cards

T = Base.metadata.tables
DEBRIEF_LOCK = "SELECT pg_advisory_xact_lock(hashtext('mona:debrief'))"


@dataclass
class Started:
    interview_id: str
    status: str
    open_questions: int | None
    reused: bool
    card_refs: list[str] = field(default_factory=list)
    questions: list[dict[str, Any]] = field(default_factory=list)


def open_questions(conn: Connection, interview_id: str) -> int:
    q = T["interview_questions"]
    return conn.execute(
        select(func.count()).where(q.c.interview_id == interview_id, q.c.status == "open")
    ).scalar_one()


def open_question_list(conn: Connection, interview_id: str) -> list[dict[str, Any]]:
    """A21: the open questions as the card shows them, in card order."""
    q, d = T["interview_questions"], T["documents"]
    rows = conn.execute(
        select(q.c.ordinal, q.c.text, q.c.affected_document_ids, q.c.options)
        .where(q.c.interview_id == interview_id, q.c.status == "open")
        .order_by(q.c.ordinal)
    ).all()
    wanted = {doc for r in rows for doc in r.affected_document_ids}
    live = set(
        conn.execute(select(d.c.id).where(d.c.id.in_(wanted), d.c.deleted_at.is_(None))).scalars()
    )
    return [
        {
            "n": r.ordinal,
            "text": r.text,
            "affected": sum(1 for doc in r.affected_document_ids if doc in live),
            "options": [o["label"] for o in r.options],
        }
        for r in rows
    ]


def _reusable(conn: Connection, interview_id: str | None) -> Mapping[str, Any] | None:
    if interview_id is None:
        return None
    i = T["interviews"]
    return (
        conn.execute(select(i).where(i.c.id == interview_id, reusable_clause())).mappings().first()
    )


def _equal_scope(conn: Connection, scope: Mapping[str, Any]) -> Mapping[str, Any] | None:
    i = T["interviews"]
    rows = conn.execute(
        select(i)
        .where(scope_filter(scope), reusable_clause())
        .order_by(i.c.created_at.desc(), i.c.id.desc())
    ).mappings()
    return next((r for r in rows if scope_equal(r["scope"], scope)), None)


def normalise_scope(conn: Connection, scope: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a requested scope (snake_case, without the snapshot)."""
    kind = scope.get("type")
    if kind == "batch":
        b = T["batches"]
        if conn.execute(select(b.c.id).where(b.c.id == scope["batch_id"])).first() is None:
            raise ServiceError("not_found", "No batch with that id.", field="batch_id")
        return {"type": "batch", "batch_id": scope["batch_id"]}
    if kind == "counterparty":
        cp = T["counterparties"]
        found = conn.execute(select(cp.c.id).where(cp.c.id == scope["counterparty_id"])).first()
        if found is None:
            raise ServiceError("not_found", "No counterparty with that id.", field="counterparty")
        return {"type": "counterparty", "counterparty_id": scope["counterparty_id"]}
    if kind == "documents":
        ids = sorted(set(scope["document_ids"]))
        if not 1 <= len(ids) <= 50:
            raise ServiceError("invalid_argument", "Give 1 to 50 documents.", field="document_ids")
        return {"type": "documents", "document_ids": ids}
    if kind in ("queue", "seed"):
        return {"type": kind}
    raise ServiceError("invalid_argument", "Unknown scope.", field="scope")


def start(
    ctx: Ctx,
    scope: Mapping[str, Any],
    *,
    lang: str | None = None,
    channel: str | None = None,
    tool: str | None = None,
    conversation_id: str | None = None,
) -> Started:
    """§2.3 reuse first, else create with a candidate snapshot; `tool` writes the card."""
    i = T["interviews"]
    with ctx.engine.begin() as conn:
        conn.execute(text(DEBRIEF_LOCK))
        wanted = normalise_scope(conn, scope)
        if lang is None:
            turn = attributed_turn(conn, channel) if channel else None
            lang = turn["reply_language"] if turn else profile_locale(conn)
        found = None
        if wanted["type"] == "batch":
            b = T["batches"]
            current = conn.execute(
                select(b.c.debrief_interview_id).where(b.c.id == wanted["batch_id"])
            ).scalar()
            found = _reusable(conn, current)
        found = found or _equal_scope(conn, wanted)
        if found is not None:
            interview_id, reused = found["id"], True
        else:
            if wanted["type"] == "seed":
                ids = seed_candidates(conn)
                full = {**wanted, "candidate_counterparty_ids": ids}
            else:
                ids = snapshot(candidates(conn, wanted, cap=False))
                full = {**wanted, "candidate_document_ids": ids}
            if not ids:
                raise ServiceError(
                    "invalid_argument", "The scope is empty: nothing to ask about.", field="scope"
                )
            interview_id, reused = create(conn, full, lang, conversation_id=conversation_id), False
        status = conn.execute(select(i.c.status).where(i.c.id == interview_id)).scalar_one()
        refs = []
        if tool is not None and channel is not None:
            refs = write_cards(conn, channel, tool, [("interview", {"interview_id": interview_id})])
        n = open_questions(conn, interview_id) if status == "ready" else None
        questions = open_question_list(conn, interview_id) if status == "ready" else []
    return Started(interview_id, status, n, reused, refs, questions)


def cancel(ctx: Ctx, interview_id: str) -> str:
    """§8: `generating` or `ready` → `cancelled`; a cancelled one stays; other finals refuse."""
    i = T["interviews"]
    with ctx.engine.begin() as conn:
        row = conn.execute(select(i).where(i.c.id == interview_id).with_for_update()).first()
        if row is None:
            raise ServiceError("not_found", "No interview with that id.")
        if row.status in ("generating", "ready"):
            conn.execute(
                update(i)
                .where(i.c.id == interview_id)
                .values(status="cancelled", finished_at=ctx.clock())
            )
            return "cancelled"
        if row.status == "cancelled":
            return "cancelled"
        raise ServiceError("conflict", "The interview is already finished.", hint="interview_final")


def sweep_stale(ctx: Ctx) -> list[str]:
    """§4.8: `generating` for 10 minutes with no live job → `failed` (`timeout`)."""
    i = T["interviews"]
    cutoff = ctx.clock() - STALE_AFTER
    with ctx.engine.begin() as conn:
        rows = (
            conn.execute(select(i.c.id).where(i.c.status == "generating", i.c.created_at < cutoff))
            .scalars()
            .all()
        )
        stale = []
        for interview_id in rows:
            live = conn.execute(
                text(
                    "SELECT 1 FROM procrastinate_jobs WHERE task_name = 'generate_interview'"
                    " AND status IN ('todo', 'doing') AND args->>'interview_id' = :id"
                ),
                {"id": interview_id},
            ).first()
            if live is None:
                stale.append(interview_id)
        if stale:
            conn.execute(
                update(i)
                .where(i.c.id.in_(stale), i.c.status == "generating")
                .values(status="failed", error="timeout")
            )
    return stale

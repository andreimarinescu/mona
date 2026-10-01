"""C6 §3: the batch and queue debrief triggers, and creating an interview with its job."""

from collections.abc import Mapping
from typing import Any

from sqlalchemy import Connection, func, insert, select, text, update

from mona.db.models import Base
from mona.ids import new_id
from mona.interviews.candidates import Doc, candidates, covered, reusable_clause, snapshot
from mona.services import Ctx
from mona.workflow.common import defer, profile_locale, settings_row

T = Base.metadata.tables
KIND_OF = {"batch": "debrief", "queue": "debrief", "seed": "seed"}


def create(
    conn: Connection,
    scope: Mapping[str, Any],
    lang: str,
    *,
    conversation_id: str | None = None,
) -> str:
    """Insert a `generating` interview and enqueue its job (C6 §4.1) in the caller's transaction."""
    i = T["interviews"]
    interview_id = new_id("int")
    conn.execute(
        insert(i).values(
            id=interview_id,
            kind=KIND_OF.get(scope["type"], "on_demand"),
            status="generating",
            scope=dict(scope),
            lang=lang,
            batch_id=scope.get("batch_id"),
            conversation_id=conversation_id,
        )
    )
    if scope["type"] == "batch":
        b = T["batches"]
        conn.execute(
            update(b).where(b.c.id == scope["batch_id"]).values(debrief_interview_id=interview_id)
        )
    defer(
        conn,
        "generate_interview",
        queue="llm",
        priority=10,
        lock=f"generate_interview:{interview_id}",
        interview_id=interview_id,
    )
    return interview_id


def uncovered(conn: Connection, scope: Mapping[str, Any]) -> list[Doc]:
    seen = covered(conn)
    return [d for d in candidates(conn, scope, cap=False) if d.id not in seen]


def _done_batch_candidates(conn: Connection) -> list[Doc]:
    b = T["batches"]
    done = set(conn.execute(select(b.c.id).where(b.c.status == "done")).scalars())
    return [d for d in uncovered(conn, {"type": "queue"}) if d.batch_id in done]


def debrief_check(ctx: Ctx, batch_id: str) -> list[str]:
    """§3.1–§3.3; returns the interviews it created (at most one per scope)."""
    created: list[str] = []
    b, i = T["batches"], T["interviews"]
    with ctx.engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('mona:debrief'))"))
        batch = (
            conn.execute(select(b).where(b.c.id == batch_id).with_for_update(key_share=True))
            .mappings()
            .first()
        )
        if batch is None:
            return created
        s = settings_row(conn)
        lang = profile_locale(conn)
        if batch["source"] == "drop" and not batch["visitor"] and not batch["debrief_interview_id"]:
            docs = uncovered(conn, {"type": "batch", "batch_id": batch_id})
            early = s.get("debrief_early_min") or 5
            if (batch["status"] == "running" and len(docs) >= early) or (
                batch["status"] == "done" and docs
            ):
                scope = {
                    "type": "batch",
                    "batch_id": batch_id,
                    "candidate_document_ids": snapshot(docs),
                }
                created.append(create(conn, scope, lang))
        queue_docs = _done_batch_candidates(conn)
        if len(queue_docs) >= s["debrief_queue_threshold"]:
            busy = conn.execute(
                select(func.count())
                .select_from(i)
                .where(i.c.scope["type"].astext == "queue", reusable_clause())
            ).scalar_one()
            if not busy:
                scope = {"type": "queue", "candidate_document_ids": snapshot(queue_docs)}
                created.append(create(conn, scope, lang))
    return created

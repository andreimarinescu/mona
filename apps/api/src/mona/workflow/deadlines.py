"""C2 §10, C4 §3.10–§3.11: the one deadline query, deadline status, and reminders."""

from collections.abc import Collection
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import Connection, Select, false, insert, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from mona import clock
from mona.chat.notes import reminder_add
from mona.db.models import Base, Batch, Deadline, Document, Entity
from mona.ids import new_id
from mona.services import Ctx, ServiceError
from mona.workflow.common import add_note, write_cards

T = Base.metadata.tables
DEADLINE_STATUSES = ("open", "done", "dismissed")


def deadline_query(
    *clauses: Any, hidden_entities: Collection[str] = (), statuses: Collection[str] = ("open",)
) -> Select:
    """Deadlines for lists and the brief: never a deleted or Visitors document's (C9 §5.5)."""
    visible = Deadline.entity_id.not_in(hidden_entities) if hidden_entities else ~false()
    return (
        select(
            Deadline.id,
            Deadline.document_id,
            Deadline.label,
            Deadline.due_date,
            Deadline.amount,
            Deadline.currency,
            Deadline.status,
            Entity.key.label("entity_key"),
            Entity.display_name.label("entity_name"),
        )
        .join(Entity, Entity.id == Deadline.entity_id)
        .outerjoin(Document, Document.id == Deadline.document_id)
        .outerjoin(Batch, Batch.id == Document.batch_id)
        .where(
            Deadline.status.in_(list(statuses)),
            Document.deleted_at.is_(None),
            Entity.purge_after_hours.is_(None),
            or_(Batch.visitor.is_(None), Batch.visitor.is_(False)),
            visible,
            *clauses,
        )
    )


def set_status(ctx: Ctx, deadline_id: str, status: str) -> None:
    """C2 §10 "Done"/Dismiss/Reopen; not journaled, and the same PATCH reverses it."""
    d = T["deadlines"]
    with ctx.engine.begin() as conn:
        n = conn.execute(
            update(d).where(d.c.id == deadline_id).values(status=status, updated_at=ctx.clock())
        ).rowcount
    if n == 0:
        raise ServiceError("not_found", "No deadline with that id.")


@dataclass
class ReminderOutcome:
    reminder_id: str
    remind_on: date
    deadline_id: str | None
    document_id: str | None
    created: bool
    card_refs: list[str] = field(default_factory=list)


def _target(conn: Connection, deadline_id: str | None, document_id: str | None) -> dict:
    d, doc, e = T["deadlines"], T["documents"], T["entities"]
    if deadline_id is not None:
        row = conn.execute(
            select(
                d.c.id,
                d.c.label,
                d.c.document_id,
                e.c.visibility,
                e.c.purge_after_hours,
                doc.c.deleted_at,
            )
            .join(e, e.c.id == d.c.entity_id)
            .outerjoin(doc, doc.c.id == d.c.document_id)
            .where(d.c.id == deadline_id)
        ).first()
        if row is None or row.deleted_at is not None:
            raise ServiceError("not_found", "No deadline with that id.")
        hidden = row.visibility == "personal" or row.purge_after_hours is not None
        return {"label": row.label, "document_id": row.document_id, "telegram_hidden": hidden}
    row = conn.execute(
        select(
            doc.c.title, doc.c.original_name, doc.c.entity_id, e.c.visibility, e.c.purge_after_hours
        )
        .outerjoin(e, e.c.id == doc.c.entity_id)
        .where(doc.c.id == document_id, doc.c.deleted_at.is_(None))
    ).first()
    if row is None:
        raise ServiceError("not_found", "No document with that id.")
    hidden = (
        row.entity_id is None or row.visibility == "personal" or row.purge_after_hours is not None
    )
    return {
        "label": row.title or row.original_name,
        "document_id": document_id,
        "telegram_hidden": hidden,
    }


def add_reminder(
    ctx: Ctx,
    *,
    deadline_id: str | None,
    document_id: str | None,
    remind_on: date,
    note: str | None,
    actor: str,
    via: str,
    channel: str = "web",
    tool: str | None = None,
    conversation_id: str | None = None,
) -> ReminderOutcome:
    """C4 §3.11 / C2 §10: idempotent on (target, `remind_on`); a `reminder.add` entry."""
    if (deadline_id is None) == (document_id is None):
        raise ServiceError(
            "invalid_argument", "Give a deadline or a document, not both.", field="deadline_id"
        )
    if remind_on < clock.paris_today(ctx.clock()):
        raise ServiceError(
            "invalid_argument", "The reminder date is in the past.", field="remind_on"
        )
    if note is not None and len(note) > 200:
        raise ServiceError("invalid_argument", "The note is at most 200 characters.", field="note")
    r = T["reminders"]
    target_key = deadline_id or document_id
    with ctx.engine.begin() as conn:
        target = _target(conn, deadline_id, document_id)
        if channel != "web" and target["telegram_hidden"]:
            raise ServiceError("not_found", "No deadline or document with that id.")
        rid = conn.execute(
            pg_insert(r)
            .values(
                id=new_id("rem"),
                deadline_id=deadline_id,
                document_id=document_id,
                remind_on=remind_on,
                note=note,
                created_by=actor,
            )
            .on_conflict_do_nothing()
            .returning(r.c.id)
        ).scalar()
        created = rid is not None
        if not created:
            rid = conn.execute(
                select(r.c.id).where(
                    (r.c.deadline_id == target_key) | (r.c.document_id == target_key),
                    r.c.remind_on == remind_on,
                    r.c.status == "scheduled",
                )
            ).scalar_one()
        else:
            conn.execute(
                insert(T["file_ops"]).values(
                    at=ctx.clock(),
                    actor=actor,
                    via=via,
                    action="reminder.add",
                    document_id=target["document_id"],
                    subject_id=rid,
                    undoable=False,
                    after={
                        "deadline_id": deadline_id,
                        "document_id": document_id,
                        "remind_on": remind_on.isoformat(),
                        "note": note,
                    },
                )
            )
        add_note(conn, conversation_id, "reminder.add", reminder_add(target["label"], remind_on))
        refs: list[str] = []
        if tool is not None:
            card = (
                ("deadline", {"deadline_id": deadline_id})
                if deadline_id
                else ("doc", {"document_id": document_id})
            )
            refs = write_cards(conn, channel, tool, [card])
    return ReminderOutcome(rid, remind_on, deadline_id, document_id, created, refs)


def cancel_reminder(ctx: Ctx, reminder_id: str) -> None:
    r = T["reminders"]
    with ctx.engine.begin() as conn:
        n = conn.execute(update(r).where(r.c.id == reminder_id).values(status="cancelled")).rowcount
    if n == 0:
        raise ServiceError("not_found", "No reminder with that id.")

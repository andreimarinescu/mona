"""`undo` (C4 §3.16, C7 §5) and delete/restore (C7 §7)."""

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select

from mona.dto import JournalEntry
from mona.fileops import FileOpError, UndoResult
from mona.services.context import Ctx
from mona.services.dto import journal_entry
from mona.services.errors import ServiceError
from mona.services.registry import T


@dataclass
class Undone:
    """C4 §3.16 result: `undone` names the entries reversed and the new entries."""

    group_id: str | None
    undone: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)


def _undone(ctx: Ctx, r: UndoResult) -> dict[str, Any]:
    d = T["documents"]
    with ctx.engine.connect() as conn:
        title = conn.execute(
            select(d.c.title, d.c.original_name).where(d.c.id == r.document_id)
        ).one()
    return {
        "journal_id": r.journal_id,
        "entry_id": r.entry_id,
        "document_id": r.document_id,
        "title": title[0] or title[1],
        "to": r.after["path"] if r.after else None,
        "location": r.after["location"] if r.after else None,
    }


def undo(
    ctx: Ctx,
    *,
    actor: str,
    via: str,
    journal_id: int | None = None,
    group_id: str | None = None,
) -> Undone:
    """Undo one entry (acting on its chain's tip) or a whole group; redo is undo of an undo."""
    if (journal_id is None) == (group_id is None):
        raise ServiceError("invalid_argument", "Give journal_id or group_id, not both.",
                           field="journal_id")  # fmt: skip
    try:
        if journal_id is not None:
            r = ctx.ops.undo(journal_id, actor=actor, via=via)
            out = Undone(None)
            if r.state == "done":
                out.undone.append(_undone(ctx, r))
            else:
                out.skipped.append({"journal_id": journal_id, "state": r.state})
            return out
        g = ctx.ops.undo_group(group_id, actor=actor, via=via)  # type: ignore[arg-type]
    except FileOpError as err:
        if err.code == "not_found":
            raise ServiceError("not_found", err.message) from None
        raise ServiceError("conflict", err.message, hint=err.hint or err.code) from None
    out = Undone(g.group_id)
    out.undone = [_undone(ctx, r) for r in g.undone]
    out.skipped = [{"journal_id": r.journal_id, "state": r.state} for r in g.skipped]
    if g.group_id is None:
        out.skipped.append({"journal_id": None, "state": g.state})
    return out


def delete_document(ctx: Ctx, document_id: str, *, actor: str, via: str) -> JournalEntry:
    """C7 §7: move to the trash; refused (`not_allowed`) for Mona."""
    try:
        r = ctx.ops.delete(document_id, actor=actor, via=via)
    except FileOpError as err:
        raise ServiceError(err.code if err.code in ("not_allowed", "not_found") else "conflict",
                           err.message, hint=err.hint) from None  # fmt: skip
    return _entry(ctx, r.entry_id, document_id)


def restore_document(ctx: Ctx, document_id: str, *, actor: str, via: str) -> JournalEntry:
    """C7 §8.4 Restore: the undo of the document's live `delete` entry."""
    f = T["file_ops"]
    with ctx.engine.connect() as conn:
        eid = conn.execute(
            select(f.c.id)
            .where(f.c.document_id == document_id, f.c.action == "delete", f.c.fs_state == "done")
            .order_by(f.c.id.desc())
            .limit(1)
        ).scalar()
    if eid is None:
        raise ServiceError("not_found", f"Document {document_id} is not in the trash.")
    r = ctx.ops.undo(eid, actor=actor, via=via)
    if r.state != "done":
        raise ServiceError("conflict", "The document can't be restored.", hint=r.state)
    return _entry(ctx, r.entry_id, document_id)


def _entry(ctx: Ctx, entry_id: int | None, document_id: str) -> JournalEntry:
    f = T["file_ops"]
    with ctx.engine.connect() as conn:
        if entry_id is None:
            entry_id = conn.execute(
                select(f.c.id).where(f.c.document_id == document_id).order_by(f.c.id.desc())
            ).scalar()
        e = conn.execute(select(f).where(f.c.id == entry_id)).mappings().one()
        return journal_entry(conn, e)

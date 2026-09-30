"""C7 §2.2 PathState and the §5.2/§5.4 live undo state."""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Connection, Table, select

from mona.db.models import Base

T: dict[str, Table] = Base.metadata.tables  # type: ignore[assignment]
UNDOABLE = frozenset({"file", "move", "rename", "unfile", "delete", "undo", "redo"})
ADOPTION_KEYS = ("adopted", "trash_copy")


def iso(dt: datetime | None) -> str | None:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z") if dt else None


def parse_ts(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def doc_state(doc: Mapping[str, Any]) -> dict[str, Any]:
    """The document's current PathState."""
    return {
        "location": doc["location"],
        "path": doc["current_path"],
        "status": doc["status"],
        "reasons": list(doc["reasons"]),
        "classification_id": doc["classification_id"],
        "rule_id": doc["rule_id"],
        "filed_by": doc["filed_by"],
        "filed_at": iso(doc["filed_at"]),
    }


def without_adoption(state: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in state.items() if k not in ADOPTION_KEYS}


def entry(conn: Connection, entry_id: int) -> Mapping[str, Any] | None:
    f = T["file_ops"]
    return conn.execute(select(f).where(f.c.id == entry_id)).mappings().first()


def chain(conn: Connection, e: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """The undo chain `e, e.undone_by, …` (§5.2); undone_by is set only by `done` entries."""
    out = [e]
    while out[-1]["undone_by"] is not None:
        nxt = entry(conn, out[-1]["undone_by"])
        if nxt is None:
            break
        out.append(nxt)
    return out


def undo_state(conn: Connection, e: Mapping[str, Any], doc: Mapping[str, Any] | None = None) -> str:
    """C7 §5.2 `JournalEntry.undoState` of a `done` entry."""
    if e["action"] not in UNDOABLE or e["document_id"] is None:
        return "not_undoable"
    c = chain(conn, e)
    if (len(c) - 1) % 2 == 1:
        return "undone"
    if doc is None:
        docs = T["documents"]
        doc = conn.execute(select(docs).where(docs.c.id == e["document_id"])).mappings().one()
    tip_after = c[-1]["after"] or {}
    if (doc["location"], doc["current_path"]) != (tip_after.get("location"), tip_after.get("path")):
        return "superseded"
    return "undoable"


def group_entries(conn: Connection, group_id: str) -> list[Mapping[str, Any]]:
    """§5.4 E: `done` entries of the group with an undoable kind, newest first."""
    f = T["file_ops"]
    q = (
        select(f)
        .where(f.c.group_id == group_id, f.c.fs_state == "done", f.c.action.in_(UNDOABLE))
        .order_by(f.c.id.desc())
    )
    return list(conn.execute(q).mappings())


def group_state(conn: Connection, group_id: str) -> tuple[str, dict[str, int]]:
    """C7 §5.4 `JournalGroup.undoState` and the C1 §11.6 counts."""
    f = T["file_ops"]
    states = [undo_state(conn, e) for e in group_entries(conn, group_id)]
    all_done = conn.execute(
        select(f.c.id).where(f.c.group_id == group_id, f.c.fs_state == "done")
    ).all()
    counts = {
        "entries": len(all_done),
        "undoable": states.count("undoable"),
        "superseded": states.count("superseded"),
        "undone": states.count("undone"),
    }
    if states and all(s == "undoable" for s in states):
        return "undoable", counts
    if counts["undoable"] == 0:
        return ("undone" if counts["undone"] else "not_undoable"), counts
    return "partial", counts


def badge_until(doc: Mapping[str, Any], badge_hours: int, now: datetime) -> datetime | None:
    """C7 §6: `filed_at + badge_hours` while a Mona filing is fresh, else None."""
    if doc["status"] != "filed" or doc["filed_by"] != "mona" or doc["filed_at"] is None:
        return None
    until = doc["filed_at"] + timedelta(hours=badge_hours)
    return until if now < until else None

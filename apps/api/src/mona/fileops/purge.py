"""C9 §5: the Visitors purge, the one hard delete of a document (C1 §10, C7 §7.5)."""

import logging
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, delete, func, select, text, update
from sqlalchemy.exc import DBAPIError

from mona.fileops.ops import FileOps, tx
from mona.fileops.roots import resolve_inside
from mona.fileops.state import T

logger = logging.getLogger(__name__)

DUE = text(
    """
    SELECT d.id, d.batch_id FROM documents d JOIN batches b ON b.id = d.batch_id
    WHERE b.visitor AND (:all OR d.arrived_at + make_interval(hours => :hours) <= :now)
    ORDER BY d.arrived_at, d.id
    """
)
EMPTY_BATCHES = text(
    """
    SELECT b.id FROM batches b
    WHERE b.visitor AND NOT EXISTS (SELECT 1 FROM documents d WHERE d.batch_id = b.id)
      AND (:all OR b.started_at + make_interval(hours => :hours) <= :now)
    ORDER BY b.started_at, b.id
    """
)


@dataclass
class Purged:
    due: list[tuple[str, str]] = field(default_factory=list)
    purged: list[str] = field(default_factory=list)
    batches: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)


def purge_hours(conn: Connection) -> int | None:
    """The Visitors entity's `purge_after_hours` (C1 §2.1); None without one."""
    e = T["entities"]
    q = select(e.c.purge_after_hours).where(e.c.purge_after_hours.isnot(None))
    return conn.execute(q).scalar()


def _unlink(root: Path, rel: str) -> Path:
    path = resolve_inside(root, rel)
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
    return path


def _files(ops: FileOps, conn: Connection, doc: Mapping[str, Any]) -> None:
    """§5.3 step 1: the document's file, a live adoption's trash copy, its caches."""
    roots = ops.roots
    path = _unlink(roots.root(doc["location"]), doc["current_path"])
    if doc["location"] in ("archive", "trash"):
        ops._tidy(roots.root(doc["location"]), path.parent)
    f = T["file_ops"]
    states = conn.execute(select(f.c.before, f.c.after).where(f.c.document_id == doc["id"]))
    copies = {s["trash_copy"] for row in states for s in row if s and s.get("trash_copy")}
    conn.rollback()
    for rel in sorted(copies):
        if rel.startswith(f"{doc['id']}/"):
            ops._tidy(roots.trash, _unlink(roots.trash, rel).parent)
    sha = doc["sha256"]
    for cached in (roots.data / "textcache" / sha[:2]).glob(f"{sha}.*"):
        cached.unlink(missing_ok=True)


def _group_tree(conn: Connection, roots: set[str]) -> dict[str, list[str]]:
    g = T["op_groups"]
    children: dict[str, list[str]] = {}
    frontier = set(roots)
    while frontier:
        rows = conn.execute(
            select(g.c.id, g.c.target_group_id).where(g.c.target_group_id.in_(frontier))
        ).all()
        frontier = set()
        for child, parent in rows:
            children.setdefault(parent, []).append(child)
            frontier.add(child)
    return children


def _delete_groups(conn: Connection, groups: set[str]) -> None:
    """§5.3 step 2.5: empty groups with their empty undo/redo chains, children first."""
    g, f = T["op_groups"], T["file_ops"]
    children = _group_tree(conn, groups)
    nodes = groups | {c for cs in children.values() for c in cs}
    busy = set(
        conn.execute(select(f.c.group_id).where(f.c.group_id.in_(nodes)).distinct()).scalars()
    )

    def empty(gid: str) -> bool:
        return gid not in busy and all(empty(c) for c in children.get(gid, []))

    def children_first(gid: str) -> list[str]:
        return [x for c in children.get(gid, []) for x in children_first(c)] + [gid]

    gone: set[str] = set()
    for root in sorted(groups):
        if root in gone or not empty(root):
            continue
        for gid in children_first(root):
            if gid not in gone:
                conn.execute(delete(g).where(g.c.id == gid))
                gone.add(gid)


def _rows(conn: Connection, doc: Mapping[str, Any]) -> bool:
    """§5.3 step 2, in one transaction; True when the batch went with its last document."""
    f, d, b = T["file_ops"], T["documents"], T["batches"]
    dl, rm = T["deadlines"], T["reminders"]
    doc_id, batch_id = doc["id"], doc["batch_id"]
    deadlines = list(conn.execute(select(dl.c.id).where(dl.c.document_id == doc_id)).scalars())
    reminders = list(
        conn.execute(
            select(rm.c.id).where((rm.c.document_id == doc_id) | rm.c.deadline_id.in_(deadlines))
        ).scalars()
    )
    entries = conn.execute(
        select(f.c.id, f.c.group_id).where(
            (f.c.document_id == doc_id) | f.c.subject_id.in_(deadlines + reminders)
        )
    ).all()
    ids = [e.id for e in entries]
    groups = {e.group_id for e in entries if e.group_id}
    conn.execute(update(d).where(d.c.filed_op_id.in_(ids)).values(filed_op_id=None))
    conn.execute(delete(f).where(f.c.id.in_(ids)))
    ce = T["card_events"]
    conn.execute(delete(ce).where(ce.c.subject["document_id"].astext == doc_id))
    conn.execute(delete(dl).where(dl.c.document_id == doc_id))
    conn.execute(delete(d).where(d.c.id == doc_id))
    left = select(func.count()).select_from(d).where(d.c.batch_id == batch_id)
    last = not conn.execute(left).scalar()
    if last:
        conn.execute(delete(T["intake_items"]).where(T["intake_items"].c.batch_id == batch_id))
        g = T["op_groups"]
        groups |= set(conn.execute(select(g.c.id).where(g.c.batch_id == batch_id)).scalars())
    _delete_groups(conn, groups)
    if last:
        conn.execute(delete(b).where(b.c.id == batch_id))
    return last


def _empty_batch(conn: Connection, batch_id: str) -> None:
    """A visitor batch with no document (only duplicates or rejects): steps 2.4–2.6."""
    g = T["op_groups"]
    conn.execute(delete(T["intake_items"]).where(T["intake_items"].c.batch_id == batch_id))
    groups = set(conn.execute(select(g.c.id).where(g.c.batch_id == batch_id)).scalars())
    _delete_groups(conn, groups)
    conn.execute(delete(T["batches"]).where(T["batches"].c.id == batch_id))


def _failed(what: str, err: DBAPIError) -> None:
    diag = getattr(err.orig, "diag", None)
    constraint = getattr(diag, "constraint_name", None)
    logger.error("purge of %s failed: %s %s", what, type(err.orig).__name__, constraint)


def purge_visitors(
    ops: FileOps,
    *,
    ignore_age: bool = False,
    dry_run: bool = False,
    crash: Callable[[str], None] | None = None,
) -> Purged:
    """C9 §5: every visitor-batch document older than the Visitors entity's
    `purge_after_hours` (all of them with `ignore_age`); files first, then the rows."""
    out = Purged()
    with ops.engine.connect() as conn:
        hours = purge_hours(conn)
        if hours is None:
            return out
        args = {"all": ignore_age, "hours": hours, "now": ops.clock()}
        out.due = [(r.id, r.batch_id) for r in conn.execute(DUE, args)]
    if dry_run:
        return out
    for doc_id, batch_id in out.due:
        with ops.locked(doc_id) as conn:
            ops._recover_document(conn, doc_id)
            d = T["documents"]
            doc = conn.execute(select(d).where(d.c.id == doc_id)).mappings().first()
            conn.rollback()
            if doc is None:
                continue
            _files(ops, conn, doc)
            if crash:
                crash(doc_id)
            try:
                with tx(conn):
                    last = _rows(conn, doc)
            except DBAPIError as err:
                _failed(doc_id, err)
                out.failed.append(doc_id)
                continue
        logger.info("purged visitor document %s (batch %s)", doc_id, batch_id)
        out.purged.append(doc_id)
        if last:
            out.batches.append(batch_id)
    with ops.engine.connect() as conn:
        empty = list(conn.execute(EMPTY_BATCHES, args).scalars())
    for batch_id in empty:
        try:
            with ops.engine.begin() as conn:
                _empty_batch(conn, batch_id)
        except DBAPIError as err:
            _failed(batch_id, err)
            out.failed.append(batch_id)
            continue
        logger.info("purged visitor batch %s", batch_id)
        out.batches.append(batch_id)
    return out


__all__ = ["Purged", "purge_hours", "purge_visitors"]

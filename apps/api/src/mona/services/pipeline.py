"""`file_document` (C5 §1.2, C7 §4) and what runs inside a filing's step C."""

import logging
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from mona.dto import DocumentSummary
from mona.fileops import Change, FileOpError
from mona.fileops.ops import error_code, keep_review
from mona.ids import new_id
from mona.services import registry
from mona.services.context import Ctx
from mona.services.dto import document_summary
from mona.services.errors import ServiceError
from mona.services.registry import T
from mona.services.search_index import rebuild_fts
from mona.templates import paris_date

RUNNING = ("queued", "reading", "ocr", "classifying", "filing")
logger = logging.getLogger(__name__)


@dataclass
class _Pending:
    settled: list[str] = field(default_factory=list)
    finished: list[str] = field(default_factory=list)


_pending: ContextVar[_Pending | None] = ContextVar("pending_hooks", default=None)


def finish_batch_if_done(
    conn: Connection, batch_id: str, now: datetime, *, settled: bool = True
) -> bool:
    """C1 §4.1: lock the batch row; `done` once no accepted document is in a running stage.

    `settled`: the transaction moved one of the batch's documents out of a running stage."""
    b, d = T["batches"], T["documents"]
    row = (
        conn.execute(select(b).where(b.c.id == batch_id).with_for_update(key_share=True))
        .mappings()
        .one()
    )
    if row["status"] == "done":
        return False
    pending = _pending.get()
    if settled and pending is not None:
        pending.settled.append(batch_id)
    left = conn.execute(
        select(func.count())
        .select_from(d)
        .where(d.c.batch_id == batch_id, d.c.pipeline_stage.in_(RUNNING))
    ).scalar_one()
    if left:
        return False
    conn.execute(update(b).where(b.c.id == batch_id).values(status="done", finished_at=now))
    if pending is not None:
        pending.finished.append(batch_id)
    return True


def _call(hook: Callable[[str], None] | None, batch_id: str) -> None:
    if hook is None:
        return
    try:
        hook(batch_id)
    except Exception as e:
        logger.error("hook for %s failed: %s", batch_id, type(e).__name__)


@contextmanager
def settle_hooks(ctx: Ctx) -> Iterator[None]:
    """C6 §3.1: after the enclosed commits, `on_document_settled` for each settle, then
    `on_batch_done` once per batch they marked `done`. Nested uses defer to the outermost;
    an exception (a rolled-back transaction) calls nothing."""
    if _pending.get() is not None:
        yield
        return
    pending = _Pending()
    token = _pending.set(pending)
    try:
        yield
    finally:
        _pending.reset(token)
    for batch_id in pending.settled:
        _call(ctx.on_document_settled, batch_id)
    for batch_id in pending.finished:
        _call(ctx.on_batch_done, batch_id)


def due_date_verified(conn: Connection, doc: Mapping[str, Any]) -> bool:
    """A verified extracted `due_date`, or one the person stated in a correction."""
    if doc["due_date"] is None:
        return False
    value = doc["due_date"].isoformat()
    ef, f = T["extraction_fields"], T["file_ops"]
    if doc["extraction_id"] is not None:
        hit = conn.execute(
            select(ef.c.key).where(
                ef.c.extraction_id == doc["extraction_id"],
                ef.c.key == "due_date",
                ef.c.verified,
                ef.c.value == value,
            )
        ).first()
        if hit:
            return True
    stated = conn.execute(
        select(f.c.after["due_date"].astext)
        .where(
            f.c.document_id == doc["id"],
            f.c.action == "doc.update",
            f.c.after.has_key("due_date"),
        )
        .order_by(f.c.id.desc())
        .limit(1)
    ).scalar()
    return stated == value


def add_extracted_deadline(
    conn: Connection, doc: Mapping[str, Any], *, actor: str, via: str, at: datetime
) -> str | None:
    """C1 §6.2: only a verified due date on or after arrival (Europe/Paris) becomes a deadline,
    and never for a document of a visitor batch (A10)."""
    if doc["entity_id"] is None or not due_date_verified(conn, doc):
        return None
    if doc["due_date"] < paris_date(doc["arrived_at"]):
        return None
    b = T["batches"]
    if conn.execute(select(b.c.visitor).where(b.c.id == doc["batch_id"])).scalar():
        return None
    t = T["deadlines"]
    money = doc["currency"] in ("EUR", "RON")
    values = {
        "id": new_id("ddl"),
        "document_id": doc["id"],
        "entity_id": doc["entity_id"],
        "label": doc["title"] or doc["doc_type"] or doc["original_name"],
        "due_date": doc["due_date"],
        "amount": doc["amount"] if money else None,
        "currency": doc["currency"] if money else None,
        "origin": "extracted",
    }
    ddl = conn.execute(
        pg_insert(t)
        .values(values)
        .on_conflict_do_nothing(
            index_elements=["document_id", "due_date"],
            index_where=t.c.document_id.isnot(None),
        )
        .returning(t.c.id)
    ).scalar()
    if ddl is None:
        return None
    after = {k: (str(v) if v is not None and k in ("due_date", "amount") else v)
             for k, v in values.items()}  # fmt: skip
    conn.execute(
        insert(T["file_ops"]).values(
            at=at, actor=actor, via=via, action="deadline.add", document_id=doc["id"],
            subject_id=ddl, after=after, undoable=False,
        )
    )  # fmt: skip
    return ddl


def fail_filing(conn: Connection, document_id: str, code: str, now: datetime) -> None:
    """C5 §1.2: a pipeline filing that failed lands in review with reason `conflict`."""
    d = T["documents"]
    doc = conn.execute(select(d).where(d.c.id == document_id).with_for_update()).mappings().one()
    if doc["location"] != "inbox" or doc["status"] != "processing":
        return
    conn.execute(
        update(d)
        .where(d.c.id == document_id)
        .values(
            pipeline_stage="failed",
            status="review",
            reasons=["conflict"],
            pipeline_error=code,
            updated_at=now,
        )
    )
    doc = conn.execute(select(d).where(d.c.id == document_id)).mappings().one()
    keep_review(conn, doc, "refiled", "mona", now)
    finish_batch_if_done(conn, doc["batch_id"], now)


def _pipeline_file(e: Mapping[str, Any]) -> bool:
    return e["action"] == "file" and e["via"] == "pipeline"


def on_commit(
    conn: Connection, e: Mapping[str, Any], doc: Mapping[str, Any], *, textcache: Path
) -> None:
    """Inside every step C (and recovery's): search index, deadlines, pipeline completion."""
    rebuild_fts(conn, doc["id"], textcache)
    if e["action"] == "file":
        add_extracted_deadline(conn, doc, actor=e["actor"], via=e["via"], at=e["at"])
    if _pipeline_file(e):
        d = T["documents"]
        conn.execute(
            update(d).where(d.c.id == doc["id"]).values(pipeline_stage="done", pipeline_error=None)
        )
        finish_batch_if_done(conn, doc["batch_id"], e["at"])


def on_failed(conn: Connection, e: Mapping[str, Any], doc: Mapping[str, Any], code: str) -> None:
    if _pipeline_file(e):
        fail_filing(conn, doc["id"], code, e["at"])


def file_document(ctx: Ctx, document_id: str) -> DocumentSummary:
    """File a classified document to its proposed path (actor `mona`, via `pipeline`).

    Filesystem failures, `forbidden_path` and `collision_exhausted` send it to review with
    reason `conflict` and the error in `pipeline_error`; the C6 hooks run after the commits."""
    d, g = T["documents"], T["op_groups"]
    with settle_hooks(ctx):
        with ctx.engine.begin() as conn:
            doc = conn.execute(select(d).where(d.c.id == document_id)).mappings().first()
            if doc is None:
                raise ServiceError("not_found", f"Unknown document {document_id}.")
            if doc["location"] != "inbox" or doc["status"] != "processing":
                return _summary(ctx, document_id)
            c = T["classifications"]
            cls = (
                conn.execute(select(c).where(c.c.id == doc["classification_id"])).mappings().first()
            )
            if cls is None or not cls["proposed_path"] or not cls["proposed_file_name"]:
                raise ServiceError("conflict", "The document has no rendered path to file to.")
            group = conn.execute(
                select(g.c.id).where(g.c.batch_id == doc["batch_id"], g.c.kind == "intake_batch")
            ).scalar()
            conn.execute(update(d).where(d.c.id == document_id).values(pipeline_stage="filing"))
        change = Change(
            document_id=document_id,
            action="file",
            location="archive",
            path=f"{cls['proposed_path']}/{cls['proposed_file_name']}",
            actor="mona",
            via="pipeline",
            expected=(doc["location"], doc["current_path"]),
            status="filed",
            reasons=(),
            classification_id=cls["id"],
            rule_id=cls["rule_id"],
            group_id=group,
            batch_id=doc["batch_id"],
            entry_rule_id=cls["rule_id"],
            confidence=cls["confidence"],
            band=cls["band"],
        )
        try:
            ctx.ops.move(change)
        except FileOpError as err:
            with ctx.engine.begin() as conn:
                fail_filing(conn, document_id, error_code(err), ctx.clock())
    return _summary(ctx, document_id)


def _summary(ctx: Ctx, document_id: str) -> DocumentSummary:
    d = T["documents"]
    with ctx.engine.connect() as conn:
        snap = registry.load(conn)
        doc = conn.execute(select(d).where(d.c.id == document_id)).mappings().one()
        return document_summary(conn, snap, doc, ctx.clock())

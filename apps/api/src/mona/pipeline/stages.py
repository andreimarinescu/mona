"""The C5 §1.2 job bodies, their retries, and the paths that end a document in review."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import Connection, insert, select, update

from mona.fileops.ops import keep_review
from mona.pipeline import cache, extract, hooks
from mona.pipeline.classify import classify
from mona.pipeline.model import ModelClient, SchemaInvalid, TransportError
from mona.pipeline.prompt import PromptBudget
from mona.pipeline.queue import defer
from mona.services.context import Ctx
from mona.services.pipeline import (
    batch_done_calls,
    file_document,
    finish_batch_if_done,
)
from mona.services.registry import T
from mona.services.search_index import rebuild_fts
from mona.text import norm

RECOVER_AFTER = timedelta(seconds=30)
HEAD_CHARS = 500


@dataclass(frozen=True)
class Retry:
    """Retries after the first attempt: `waits[n]` seconds before attempt n + 2."""

    waits: tuple[int, ...] = ()
    on: tuple[type[BaseException], ...] = (Exception,)

    def will_retry(self, exc: BaseException, attempts: int) -> bool:
        return attempts < len(self.waits) and isinstance(exc, self.on)


RETRY = {
    "extract_text": Retry((10, 10)),
    "render_thumbnail": Retry((10,)),
    "classify_document": Retry((5, 20), (TransportError, SchemaInvalid)),
    "file_document": Retry(),
}


def error_code(exc: BaseException) -> str:
    """`pipeline_error`: the error class, never document text."""
    if isinstance(exc, PromptBudget):
        return "prompt_budget"
    return type(exc).__name__


# --- the settle paths (C5 §1.2): each is one transaction with the batch-done check ---


def _settle(
    ctx: Ctx, document_id: str, values: dict[str, Any], *, running_only: bool = True,
    journal: Callable[[Connection, Mapping[str, Any]], None] | None = None,
) -> bool:  # fmt: skip
    """Move a document out of its running stage; False if it had already left one."""
    d = T["documents"]
    now = ctx.clock()
    with ctx.engine.begin() as conn:
        doc = conn.execute(select(d).where(d.c.id == document_id).with_for_update()).mappings()
        doc = doc.first()
        if doc is None or (running_only and doc["status"] != "processing"):
            return False
        conn.execute(update(d).where(d.c.id == document_id).values(updated_at=now, **values))
        doc = conn.execute(select(d).where(d.c.id == document_id)).mappings().one()
        if journal:
            journal(conn, doc)
        keep_review(conn, doc, "refiled", "mona", now)
        finished = finish_batch_if_done(conn, doc["batch_id"], now)
    hooks.document_settled(ctx, doc["batch_id"])
    if finished:
        hooks.batch_done(ctx, doc["batch_id"])
    return True


def _mark_unreadable(ctx: Ctx) -> Callable[[Connection, Mapping[str, Any]], None]:
    def write(conn: Connection, doc: Mapping[str, Any]) -> None:
        g = T["op_groups"]
        group = conn.execute(
            select(g.c.id).where(g.c.batch_id == doc["batch_id"], g.c.kind == "intake_batch")
        ).scalar()
        conn.execute(
            insert(T["file_ops"]).values(
                at=ctx.clock(), actor="mona", via="pipeline", action="mark.unreadable",
                document_id=doc["id"], sha256=doc["sha256"], before={"status": "processing"},
                after={"status": "unreadable", "reasons": ["unreadable"]},
                batch_id=doc["batch_id"], group_id=group, undoable=False,
            )
        )  # fmt: skip

    return write


def unreadable(ctx: Ctx, document_id: str) -> bool:
    """Fewer than 50 non-whitespace characters: no model call, straight to review."""
    return _settle(
        ctx, document_id,
        {"status": "unreadable", "reasons": ["unreadable"], "pipeline_stage": "done",
         "pipeline_error": None},
        journal=_mark_unreadable(ctx),
    )  # fmt: skip


def _failed(status: str, reason: str, code: str) -> dict[str, Any]:
    return {"status": status, "reasons": [reason], "pipeline_stage": "failed",
            "pipeline_error": code}  # fmt: skip


def fail_extraction(ctx: Ctx, document_id: str, code: str) -> bool:
    return _settle(ctx, document_id, _failed("unreadable", "unreadable", code))


def fail_classification(ctx: Ctx, document_id: str, code: str) -> bool:
    return _settle(ctx, document_id, _failed("review", "low", code))


def skip_deleted(ctx: Ctx, document_id: str) -> bool:
    """A document deleted mid-pipeline stops, so its batch can still finish."""
    d = T["documents"]
    with ctx.engine.connect() as conn:
        deleted = conn.execute(select(d.c.deleted_at).where(d.c.id == document_id)).scalar()
    if deleted is None:
        return False
    return _settle(ctx, document_id, {"pipeline_stage": "done"}, running_only=False)


# --- job bodies ---


def _stage(ctx: Ctx, document_id: str, stage: str) -> Mapping[str, Any] | None:
    d = T["documents"]
    with ctx.engine.begin() as conn:
        doc = conn.execute(select(d).where(d.c.id == document_id).with_for_update()).mappings()
        doc = doc.first()
        if doc is None or doc["status"] != "processing":
            return None
        conn.execute(update(d).where(d.c.id == document_id).values(pipeline_stage=stage))
        return doc


def extract_text(ctx: Ctx, document_id: str, runner: extract.Runner = extract.run) -> str:
    if skip_deleted(ctx, document_id):
        return "skipped"
    doc = _stage(ctx, document_id, "reading")
    if doc is None:
        return "skipped"
    src = ctx.ops.roots.root(doc["location"]) / doc["current_path"]
    pages = extract.extract(
        src, doc["mime_type"], doc["sha256"], ctx.textcache, runner,
        on_ocr=lambda: _stage(ctx, document_id, "ocr"),
    )  # fmt: skip
    if sum(extract.solid_chars(p) for p in pages.pages) < extract.UNREADABLE_MIN:
        _set_text_fields(ctx, document_id, pages)
        unreadable(ctx, document_id)
        return "unreadable"
    d = T["documents"]
    with ctx.engine.begin() as conn:
        live = conn.execute(select(d.c.status).where(d.c.id == document_id).with_for_update())
        if live.scalar() != "processing":
            return "skipped"
        _text_fields(conn, document_id, pages)
        rebuild_fts(conn, document_id, ctx.textcache)
        defer(conn, "render_thumbnail", document_id)
        defer(conn, "classify_document", document_id)
    return pages.method


def _text_fields(conn: Connection, document_id: str, pages: cache.Pages) -> None:
    d = T["documents"]
    head = norm(pages.pages[0][:HEAD_CHARS]) if pages.pages else None
    conn.execute(
        update(d).where(d.c.id == document_id)
        .values(page_count=pages.page_count, head_norm=head or None)
    )  # fmt: skip


def _set_text_fields(ctx: Ctx, document_id: str, pages: cache.Pages) -> None:
    with ctx.engine.begin() as conn:
        _text_fields(conn, document_id, pages)


def render_thumbnail(ctx: Ctx, document_id: str, runner: extract.Runner = extract.run) -> str:
    d = T["documents"]
    with ctx.engine.connect() as conn:
        doc = conn.execute(select(d).where(d.c.id == document_id)).mappings().first()
    if doc is None:
        return "skipped"
    src = ctx.ops.roots.root(doc["location"]) / doc["current_path"]
    pdf = extract.viewer_pdf(src, doc["mime_type"], ctx.textcache, doc["sha256"])
    if pdf is None:
        return "skipped"
    extract.thumbnail(pdf, ctx.textcache, doc["sha256"], runner)
    return "done"


def classify_document(ctx: Ctx, document_id: str, model: ModelClient) -> str:
    if skip_deleted(ctx, document_id):
        return "skipped"
    return classify(ctx, document_id, model).outcome


def file_stage(ctx: Ctx, document_id: str) -> str:
    if skip_deleted(ctx, document_id):
        return "skipped"
    summary = file_document(ctx, document_id)
    hooks.document_settled(ctx, summary.batch_id)
    return summary.status


def fail_filing_stage(ctx: Ctx, document_id: str, code: str) -> bool:
    """A non-file-op error in `file_document`: to review unless recovery owns a pending entry."""
    f = T["file_ops"]
    with ctx.engine.connect() as conn:
        pending = conn.execute(
            select(f.c.id).where(f.c.document_id == document_id, f.c.fs_state == "pending")
        ).first()
    if pending is not None:
        return False
    return _settle(ctx, document_id, _failed("review", "conflict", code))


FAIL: dict[str, Callable[[Ctx, str, str], bool] | None] = {
    "extract_text": fail_extraction,
    "render_thumbnail": None,
    "classify_document": fail_classification,
    "file_document": fail_filing_stage,
}


def run(
    ctx: Ctx, job: str, document_id: str, *, attempts: int = 0,
    model: Callable[[], ModelClient] | None = None, runner: extract.Runner = extract.run,
) -> str:  # fmt: skip
    """One attempt of a job. A retryable error is raised for Procrastinate to retry; the last
    failure takes the job's failure path and returns `failed`."""
    try:
        if job == "extract_text":
            return extract_text(ctx, document_id, runner)
        if job == "render_thumbnail":
            return render_thumbnail(ctx, document_id, runner)
        if job == "classify_document":
            assert model is not None
            return classify_document(ctx, document_id, model())
        if job == "file_document":
            return file_stage(ctx, document_id)
        raise ValueError(job)
    except Exception as e:
        if RETRY[job].will_retry(e, attempts):
            raise
        fail = FAIL[job]
        if fail is not None:
            fail(ctx, document_id, error_code(e))
        return "failed"


def recover(ctx: Ctx, older_than: timedelta = RECOVER_AFTER) -> dict[int, str]:
    """C7 §4.3 recovery; pipeline filings it fails land in review (M1's hook)."""
    with batch_done_calls(ctx):
        return ctx.ops.recover_pending(older_than)

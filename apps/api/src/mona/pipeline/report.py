"""`mona pipeline run` output: each document's outcome and per-stage job timings."""

import time
from collections.abc import Callable
from typing import Any

from sqlalchemy import select, text

from mona.services.context import Ctx
from mona.services.registry import T

STAGE_TIMES = text(
    """
    SELECT j.args->>'document_id' AS document_id, j.task_name,
           min(e.at) FILTER (WHERE e.type = 'started') AS started,
           max(e.at) FILTER (WHERE e.type IN ('succeeded', 'failed')) AS ended
    FROM procrastinate_jobs j JOIN procrastinate_events e ON e.job_id = j.id
    WHERE j.args->>'document_id' = ANY(:ids)
    GROUP BY 1, 2
    """
)


def wait_for_batch(
    ctx: Ctx, batch_id: str, timeout: float, step: Callable[[], None] | None = None
) -> bool:
    b = T["batches"]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if step:
            step()
        with ctx.engine.connect() as conn:
            if conn.execute(select(b.c.status).where(b.c.id == batch_id)).scalar() == "done":
                return True
        time.sleep(1)
    return False


def batch_report(ctx: Ctx, batch_id: str) -> list[dict[str, Any]]:
    d, it, x = T["documents"], T["intake_items"], T["extractions"]
    with ctx.engine.connect() as conn:
        items = conn.execute(
            select(it).where(it.c.batch_id == batch_id).order_by(it.c.created_at, it.c.id)
        ).mappings().all()  # fmt: skip
        ids = [i["document_id"] for i in items if i["outcome"] == "accepted"]
        docs = {r["id"]: r for r in conn.execute(select(d).where(d.c.id.in_(ids))).mappings()}
        exts = {
            r["id"]: r for r in conn.execute(select(x).where(x.c.document_id.in_(ids))).mappings()
        }
        stages: dict[str, dict[str, float]] = {}
        for r in conn.execute(STAGE_TIMES, {"ids": ids}):
            if r.started and r.ended:
                seconds = (r.ended - r.started).total_seconds()
                stages.setdefault(r.document_id, {})[r.task_name] = round(seconds, 2)
    rows = []
    for i in items:
        row: dict[str, Any] = {
            "name": i["original_name"],
            "sha12": i["sha256"][:12],
            "outcome": i["outcome"],
            "document_id": i["document_id"],
        }
        doc = docs.get(i["document_id"]) if i["outcome"] == "accepted" else None
        if doc is not None:
            ext = exts.get(doc["extraction_id"])
            row |= {
                "status": doc["status"], "stage": doc["pipeline_stage"],
                "reasons": list(doc["reasons"]), "band": doc["band"],
                "confidence": doc["confidence"],
                "path": doc["current_path"] if doc["location"] == "archive" else None,
                "error": doc["pipeline_error"], "stages": stages.get(doc["id"], {}),
                "model_ms": ext["duration_ms"] if ext else None,
                "from_cache": ext["from_cache"] if ext else None,
                "wall_s": round((doc["updated_at"] - doc["arrived_at"]).total_seconds(), 2),
            }  # fmt: skip
        rows.append(row)
    return rows


def format_report(rows: list[dict[str, Any]]) -> str:
    out = []
    for r in rows:
        if "status" not in r:
            out.append(f"{r['sha12']}  {r['outcome']}")
            continue
        stages = " ".join(f"{k}={v}s" for k, v in sorted(r["stages"].items()))
        where = r["path"] or ",".join(r["reasons"]) or r["stage"]
        out.append(
            f"{r['sha12']}  {r['status']:<10} {r['band'] or '-':<6} {r['confidence'] or '-':>3}  "
            f"{where}  [{stages}]"
        )
    return "\n".join(out)


def evidence_cases(ctx: Ctx, batch_id: str | None = None) -> list[dict[str, Any]]:
    """Every verified quote's `findQuery` with the PDF the viewer opens and its page: the input
    of the pdf.js check (`apps/web/e2e/findquery.spec.ts`)."""
    from mona.pipeline import cache
    from mona.pipeline.extract import viewer_pdf

    d, ef = T["documents"], T["extraction_fields"]
    q = (
        select(d.c.id, d.c.location, d.c.current_path, d.c.mime_type, d.c.sha256, ef.c.key,
               ef.c.page, ef.c.quote, ef.c.find_query)
        .join(ef, ef.c.extraction_id == d.c.extraction_id)
        .where(d.c.deleted_at.is_(None), ef.c.verified, ef.c.find_query.isnot(None))
        .order_by(d.c.arrived_at, d.c.id, ef.c.key)
    )  # fmt: skip
    if batch_id:
        q = q.where(d.c.batch_id == batch_id)
    out = []
    with ctx.engine.connect() as conn:
        for r in conn.execute(q):
            src = ctx.ops.roots.root(r.location) / r.current_path
            pdf = viewer_pdf(src, r.mime_type, ctx.textcache, r.sha256)
            pages = cache.read_pages(ctx.textcache, r.sha256)
            out.append({
                "document_id": r.id, "field": r.key, "page": r.page, "quote": r.quote,
                "find_query": r.find_query, "pdf": str(pdf) if pdf else None,
                "method": pages.method if pages else None,
            })  # fmt: skip
    return out

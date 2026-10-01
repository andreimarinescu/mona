"""C4 §3.13, C2 §12, C9 §3.3: the accountant pack (a zip plus a formula-safe CSV index)."""

import csv
import io
import logging
import os
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, func, insert, select, update

from mona.db.models import Base
from mona.i18n import t
from mona.ids import new_id
from mona.services import Ctx, ServiceError
from mona.templates import slug
from mona.workflow.common import defer, settings_row, write_cards

logger = logging.getLogger(__name__)
T = Base.metadata.tables
FORMULA_START = ("=", "+", "-", "@", "\t", "\r")
COLUMNS = (
    "file",
    "title",
    "date",
    "counterparty",
    "reference",
    "category",
    "subcategory",
    "amount",
    "currency",
    "dueDate",
)


def cell(value: Any) -> str:
    """C4 §3.13: a cell that could start a formula is prefixed with `'`."""
    s = "" if value is None else str(value)
    return "'" + s if s.startswith(FORMULA_START) else s


def exports_root(ctx: Ctx) -> Path:
    return ctx.data_dir / "exports"


def exportable(conn: Connection, entity_id: str) -> Any:
    """The entity, or `not_allowed` for a personal or the Visitors entity (every channel)."""
    e = T["entities"]
    row = conn.execute(select(e).where(e.c.id == entity_id)).mappings().first()
    if row is None:
        raise ServiceError("not_found", "No entity with that id.")
    if row["visibility"] == "personal" or row["purge_after_hours"] is not None:
        raise ServiceError("not_allowed", "Personal entities and Visitors can't be exported.")
    return row


def _selection(entity_id: str, fiscal_year: int) -> list[Any]:
    """C9 §3.1 `export` column: filed, not deleted, entity E, fiscal year Y."""
    d = T["documents"]
    return [
        d.c.entity_id == entity_id,
        d.c.fiscal_year == fiscal_year,
        d.c.status == "filed",
        d.c.deleted_at.is_(None),
        d.c.location == "archive",
    ]


def preview(conn: Connection, entity_id: str, fiscal_year: int, lang: str) -> dict[str, Any]:
    exportable(conn, entity_id)
    d, c = T["documents"], T["categories"]
    count = conn.execute(
        select(func.count()).select_from(d).where(*_selection(entity_id, fiscal_year))
    ).scalar_one()
    in_review = conn.execute(
        select(func.count())
        .select_from(d)
        .where(
            d.c.entity_id == entity_id,
            d.c.fiscal_year == fiscal_year,
            d.c.status == "review",
            d.c.deleted_at.is_(None),
        )
    ).scalar_one()
    cats = conn.execute(
        select(c.c.id, c.c.labels, func.count(d.c.id))
        .join(d, d.c.category_id == c.c.id)
        .where(*_selection(entity_id, fiscal_year))
        .group_by(c.c.id, c.c.labels, c.c.sort_order)
        .order_by(c.c.sort_order, c.c.id)
    ).all()
    years = (
        conn.execute(
            select(func.distinct(d.c.fiscal_year))
            .where(
                d.c.entity_id == entity_id, d.c.fiscal_year.is_not(None), d.c.deleted_at.is_(None)
            )
            .order_by(d.c.fiscal_year.desc())
        )
        .scalars()
        .all()
    )
    return {
        "entity_id": entity_id,
        "fiscal_year": fiscal_year,
        "document_count": count,
        "in_review": in_review,
        "categories": [
            {"id": i, "label": labels.get(lang, i), "count": n} for i, labels, n in cats
        ],
        "fiscal_years": list(years),
    }


@dataclass
class Started:
    export_id: str
    status: str
    document_count: int | None
    created: bool
    card_refs: list[str] = field(default_factory=list)


def start_export(
    ctx: Ctx, entity_id: str, fiscal_year: int, *, channel: str = "web", tool: str | None = None
) -> Started:
    """The export building for the same entity and year, else a new one and its job."""
    x, d = T["exports"], T["documents"]
    with ctx.engine.begin() as conn:
        exportable(conn, entity_id)
        conn.execute(
            select(T["entities"].c.id)
            .where(T["entities"].c.id == entity_id)
            .with_for_update(key_share=True)
        )
        row = (
            conn.execute(
                select(x)
                .where(
                    x.c.entity_id == entity_id,
                    x.c.fiscal_year == fiscal_year,
                    x.c.status == "building",
                )
                .order_by(x.c.created_at.desc())
            )
            .mappings()
            .first()
        )
        created = row is None
        if created:
            count = conn.execute(
                select(func.count()).select_from(d).where(*_selection(entity_id, fiscal_year))
            ).scalar_one()
            export_id = new_id("exp")
            conn.execute(
                insert(x).values(
                    id=export_id, entity_id=entity_id, fiscal_year=fiscal_year, document_count=count
                )
            )
            defer(
                conn,
                "build_export",
                queue="cpu",
                priority=0,
                lock=f"build_export:{export_id}",
                export_id=export_id,
            )
        else:
            export_id, count = row["id"], row["document_count"]
        refs = (
            write_cards(conn, channel, tool, [("export", {"export_id": export_id})]) if tool else []
        )
    return Started(export_id, "building", count, created, refs)


def _rows(conn: Connection, entity_id: str, fiscal_year: int, lang: str) -> list[dict[str, Any]]:
    d, c, s, cp = T["documents"], T["categories"], T["subcategories"], T["counterparties"]
    q = (
        select(
            d,
            c.c.labels.label("cat_labels"),
            s.c.labels.label("sub_labels"),
            cp.c.name.label("cp_name"),
        )
        .outerjoin(c, c.c.id == d.c.category_id)
        .outerjoin(s, (s.c.category_id == d.c.category_id) & (s.c.key == d.c.subcategory_key))
        .outerjoin(cp, cp.c.id == d.c.counterparty_id)
        .where(*_selection(entity_id, fiscal_year))
        .order_by(d.c.current_path)
    )
    return [dict(r) for r in conn.execute(q).mappings()]


def build_export(ctx: Ctx, export_id: str) -> str:
    x, e = T["exports"], T["entities"]
    with ctx.engine.connect() as conn:
        exp = conn.execute(select(x).where(x.c.id == export_id)).mappings().first()
        if exp is None or exp["status"] != "building":
            return "skipped"
        ent = conn.execute(select(e).where(e.c.id == exp["entity_id"])).mappings().one()
        lang = ent["filing_language"] or settings_row(conn)["filing_language"]
        docs = _rows(conn, exp["entity_id"], exp["fiscal_year"], lang)
    try:
        name = f"{slug(ent['folder_name']) or 'export'}_{exp['fiscal_year']}"
        folder = exports_root(ctx) / export_id
        folder.mkdir(parents=True, exist_ok=True)
        csv_bytes = _csv(docs, lang)
        zip_tmp = folder / f"{name}.zip.tmp"
        with zipfile.ZipFile(zip_tmp, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for doc in docs:
                z.write(ctx.ops.roots.archive / doc["current_path"], arcname=doc["current_path"])
            z.writestr(f"{name}.csv", csv_bytes)
        csv_tmp = folder / f"{name}.csv.tmp"
        csv_tmp.write_bytes(csv_bytes)
        os.replace(zip_tmp, folder / f"{name}.zip")
        os.replace(csv_tmp, folder / f"{name}.csv")
        values = {
            "status": "ready",
            "document_count": len(docs),
            "error": None,
            "zip_path": f"{export_id}/{name}.zip",
            "csv_path": f"{export_id}/{name}.csv",
        }
    except OSError as err:
        logger.warning("export %s failed: %s", export_id, type(err).__name__)
        values = {"status": "failed", "error": type(err).__name__}
    with ctx.engine.begin() as conn:
        conn.execute(update(x).where(x.c.id == export_id).values(updated_at=ctx.clock(), **values))
    return values["status"]


def _csv(docs: list[dict[str, Any]], lang: str) -> bytes:
    """C9 §3.3: titles, counterparties and references only; no IBAN, quote or page text."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow([t(f"export.csv.{c}", lang) for c in COLUMNS])
    for doc in docs:
        w.writerow(
            [
                cell(v)
                for v in (
                    doc["current_path"],
                    doc["title"] or doc["original_name"],
                    doc["doc_date"].isoformat() if doc["doc_date"] else None,
                    doc["cp_name"],
                    doc["reference"],
                    (doc["cat_labels"] or {}).get(lang),
                    (doc["sub_labels"] or {}).get(lang),
                    f"{doc['amount']:.2f}" if doc["amount"] is not None else None,
                    doc["currency"],
                    doc["due_date"].isoformat() if doc["due_date"] else None,
                )
            ]
        )
    return buf.getvalue().encode("utf-8-sig")


def file_path(ctx: Ctx, export_id: str, kind: str) -> tuple[Path, str]:
    """The ready pack's zip or CSV; `not_found` (hint `not_ready`) before that."""
    x = T["exports"]
    with ctx.engine.connect() as conn:
        exp = conn.execute(select(x).where(x.c.id == export_id)).mappings().first()
    if exp is None:
        raise ServiceError("not_found", "No export with that id.")
    rel = exp["zip_path" if kind == "zip" else "csv_path"]
    if exp["status"] != "ready" or not rel:
        raise ServiceError("not_found", "The pack isn't ready.", hint="not_ready")
    path = exports_root(ctx) / rel
    if not path.is_file():
        raise ServiceError("not_found", "The pack file is missing.", hint="not_ready")
    return path, path.name

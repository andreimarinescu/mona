"""A31 `export_table`: a CSV, XLSX or DOCX table of documents, built while the tool runs."""

import csv
import io
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from docx import Document as DocxDocument
from docx.enum.section import WD_ORIENT
from docx.shared import Pt
from openpyxl import Workbook
from openpyxl.styles import Font
from sqlalchemy import insert

from mona.i18n import format_date, format_money, t
from mona.ids import new_id
from mona.services import Ctx, ServiceError
from mona.templates import slug
from mona.workflow.common import attributed_turn, profile_locale, write_cards
from mona.workflow.exports import T, cell, exports_root

logger = logging.getLogger(__name__)

Format = Literal["csv", "xlsx", "docx"]
Column = Literal[
    "title", "counterparty", "entity", "category", "doc_date", "due_date", "amount", "currency",
    "payment_iban", "reference", "status", "path",
]  # fmt: skip
MAX_ROWS = 500
MEDIA = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
XLSX_DATE = {"en": "d mmm yyyy", "fr": "dd/mm/yyyy", "ro": "dd.mm.yyyy"}
_SHEET_BAD = re.compile(r"[\[\]:*?/\\]")


@dataclass
class Table:
    title: str
    columns: list[str]
    rows: list[dict[str, Any]]
    lang: str


def _header(column: str, lang: str) -> str:
    return t(f"export.table.column.{column}", lang)


def _status(value: str | None, lang: str) -> str | None:
    return t(f"export.table.status.{value}", lang) if value else None


def csv_bytes(table: Table) -> bytes:
    """ISO dates, dot decimals, column keys as headers, and C4 §3.13's formula guard."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(table.columns)
    for row in table.rows:
        out = []
        for c in table.columns:
            v = row.get(c)
            if isinstance(v, date):
                out.append(v.isoformat())
            elif isinstance(v, Decimal):
                out.append(f"{v:.2f}")
            else:
                out.append(cell(v))
        w.writerow(out)
    return buf.getvalue().encode("utf-8-sig")


def xlsx_bytes(table: Table) -> bytes:
    """Typed cells: dates as dates, amounts as numbers, text always text (never a formula)."""
    wb = Workbook()
    ws = wb.active
    ws.title = (_SHEET_BAD.sub(" ", table.title).strip("' ") or "Table")[:31]
    ws.append([_header(c, table.lang) for c in table.columns])
    for c in ws[1]:
        c.font = Font(bold=True)
    ws.freeze_panes = "A2"
    for n, row in enumerate(table.rows, start=2):
        for col, key in enumerate(table.columns, start=1):
            v = row.get(key)
            if key == "status":
                v = _status(v, table.lang)
            target = ws.cell(row=n, column=col)
            if isinstance(v, date):
                target.value = v
                target.number_format = XLSX_DATE[table.lang]
            elif isinstance(v, Decimal):
                target.value = float(v)
                target.number_format = "#,##0.00"
            elif v is not None:
                target.value = str(v)
                target.data_type = "s"
    for col, key in enumerate(table.columns, start=1):
        width = max(
            [len(_header(key, table.lang))] + [len(str(r.get(key) or "")) for r in table.rows]
        )
        ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = min(width + 2, 60)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _docx_value(row: dict[str, Any], key: str, lang: str) -> str:
    v = row.get(key)
    if v is None:
        return ""
    if key == "amount" and row.get("currency") in ("EUR", "RON"):
        return format_money(v, row["currency"], lang)
    if key == "status":
        return _status(v, lang) or ""
    if isinstance(v, date):
        return format_date(v, lang)
    return str(v)


def docx_bytes(table: Table) -> bytes:
    """C8: a titled table, dates and amounts written for the request's locale."""
    doc = DocxDocument()
    doc.core_properties.title = table.title
    if len(table.columns) > 5:
        s = doc.sections[0]
        s.orientation = WD_ORIENT.LANDSCAPE
        s.page_width, s.page_height = s.page_height, s.page_width
    doc.add_heading(table.title, level=1)
    grid = doc.add_table(rows=1, cols=len(table.columns))
    grid.style = "Table Grid"
    for c, key in zip(grid.rows[0].cells, table.columns, strict=True):
        c.text = ""
        c.paragraphs[0].add_run(_header(key, table.lang)).bold = True
    for row in table.rows:
        cells = grid.add_row().cells
        for c, key in zip(cells, table.columns, strict=True):
            c.text = _docx_value(row, key, table.lang)
    for r in grid.rows:
        for c in r.cells:
            for p in c.paragraphs:
                for run in p.runs:
                    run.font.size = Pt(9)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


BUILDERS = {"csv": csv_bytes, "xlsx": xlsx_bytes, "docx": docx_bytes}


@dataclass
class Made:
    export_id: str
    file_name: str
    rows: int
    truncated: bool
    card_refs: list[str] = field(default_factory=list)


def make(
    ctx: Ctx,
    *,
    columns: list[str],
    rows: list[dict[str, Any]],
    truncated: bool,
    fmt: Format,
    title: str | None,
    lang: str | None,
    channel: str,
    via: str,
    tool: str | None = None,
) -> Made:
    """Write the file under the exports folder, its `exports` row, the activity entry and card."""
    x = T["exports"]
    with ctx.engine.begin() as conn:
        if lang is None:
            turn = attributed_turn(conn, channel)
            lang = turn["reply_language"] if turn else profile_locale(conn)
        labels = {r.id: r.labels for r in conn.execute(T["categories"].select())}
        shown = [
            {**r, "category": (labels.get(r["category"]) or {}).get(lang, r["category"])}
            if r.get("category") else r
            for r in rows
        ]  # fmt: skip
        title = (title or "").strip() or t("export.table.defaultTitle", lang)
        export_id = new_id("exp")
        name = f"{slug(title)[:60].strip('-.') or 'table'}.{fmt}"
        data = BUILDERS[fmt](Table(title, columns, shown, lang))
        folder = exports_root(ctx) / export_id
        try:
            folder.mkdir(parents=True, exist_ok=True)
            tmp = folder / f"{name}.tmp"
            tmp.write_bytes(data)
            os.replace(tmp, folder / name)
        except OSError as err:
            logger.warning("table export %s failed: %s", export_id, type(err).__name__)
            raise ServiceError(
                "conflict", "The file couldn't be written.", hint=type(err).__name__
            ) from None
        conn.execute(
            insert(x).values(
                id=export_id, status="ready", document_count=len(rows), format=fmt,
                title=title, file_path=f"{export_id}/{name}", truncated=truncated,
            )
        )  # fmt: skip
        conn.execute(
            insert(T["file_ops"]).values(
                at=ctx.clock(), actor="mona", via=via, action="export", subject_id=export_id,
                undoable=False,
                after={"format": fmt, "rows": len(rows), "file_name": name, "truncated": truncated},
            )
        )  # fmt: skip
        refs = (
            write_cards(conn, channel, tool, [("export", {"export_id": export_id})]) if tool else []
        )
    return Made(export_id, name, len(rows), truncated, refs)

"""A31 `export_table`: a CSV, XLSX or DOCX table of documents, built while the tool runs; A36:
the inline table, kept as a spec and built from current state when shown."""

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
from sqlalchemy import Connection, Select, func, insert, select

from mona.chat.notes import table_download
from mona.db.models import Category, Counterparty, Document, Entity
from mona.dto.enums import TableColumnKey
from mona.i18n import format_date, format_money, t
from mona.ids import new_id
from mona.mcp.filters import STATUSES
from mona.pipeline.payment_iban import mask
from mona.services import Ctx, ServiceError
from mona.templates import slug
from mona.visibility import Scope
from mona.workflow.common import add_note, attributed_turn, profile_locale, write_cards
from mona.workflow.exports import T, cell, exports_root

logger = logging.getLogger(__name__)

FileFormat = Literal["csv", "xlsx", "docx"]
Format = Literal["csv", "xlsx", "docx", "table"]
Column = TableColumnKey
MAX_ROWS = 500
SHOWN = 50
TELEGRAM_ROWS = 20
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


def row_select(*clauses: Any) -> Select:
    """The table's columns for documents matching `clauses`."""
    return (
        select(
            Document.id,
            func.coalesce(Document.title, Document.original_name).label("title"),
            Counterparty.name.label("counterparty"),
            Entity.display_name.label("entity"),
            Category.id.label("category"),
            Document.doc_date,
            Document.due_date,
            Document.amount,
            Document.currency,
            Document.payment_iban,
            Document.reference,
            Document.status,
            Document.location,
            Document.current_path,
        )
        .outerjoin(Entity, Entity.id == Document.entity_id)
        .outerjoin(Category, Category.id == Document.category_id)
        .outerjoin(Counterparty, Counterparty.id == Document.counterparty_id)
        .where(*clauses)
    )


def row_values(r: Any, ch: str) -> dict[str, Any]:
    return {
        "title": r.title,
        "counterparty": r.counterparty,
        "entity": r.entity,
        "category": r.category,
        "doc_date": r.doc_date,
        "due_date": r.due_date,
        "amount": r.amount,
        "currency": r.currency if r.amount is not None else None,
        "payment_iban": mask(r.payment_iban) if ch == "telegram" else r.payment_iban,
        "reference": r.reference,
        "status": r.status,
        "path": r.current_path if r.location == "archive" else None,
    }


async def spec_rows(scope: Scope, document_ids: list[str]) -> list[dict[str, Any]]:
    """A36: the spec's documents still visible on the channel, in table order."""
    if not document_ids:
        return []
    stmt = row_select(
        *scope.document_clauses(),
        Document.status.in_(STATUSES["any"]),
        Document.id.in_(document_ids),
    )
    found = {r.id: r for r in (await scope.conn.execute(stmt)).all()}
    return [row_values(found[d], scope.channel) for d in document_ids if d in found]


def empty_columns(columns: list[str], rows: list[dict[str, Any]]) -> list[str]:
    """A35: the requested columns with no value in any row, in request order."""
    return [c for c in columns if all(r.get(c) in (None, "") for r in rows)]


def labelled(
    rows: list[dict[str, Any]], labels: dict[str, dict[str, str]], lang: str
) -> list[dict[str, Any]]:
    """Category ids replaced by their label in `lang`."""
    return [
        {**r, "category": (labels.get(r["category"]) or {}).get(lang, r["category"])}
        if r.get("category") else r
        for r in rows
    ]  # fmt: skip


def view_rows(rows: list[dict[str, Any]], columns: list[str], lang: str) -> list[dict[str, Any]]:
    """C3 `TableView` rows: ISO dates, numeric amounts with `currency`, labels in `lang`."""
    out = []
    for row in rows:
        keys = [*columns, "currency"] if "amount" in columns else columns
        cells: dict[str, Any] = {}
        for key in keys:
            v = row.get(key)
            if key == "status":
                v = _status(v, lang)
            elif isinstance(v, date):
                v = v.isoformat()
            elif isinstance(v, Decimal):
                v = float(v)
            cells[key] = v
        out.append(cells)
    return out


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


def telegram_text(table: Table) -> str:
    """A36 on Telegram: the title, the column names, then one line per row (at most 20)."""
    lines = [table.title, " · ".join(_header(c, table.lang) for c in table.columns)]
    for row in table.rows[:TELEGRAM_ROWS]:
        cells = [_docx_value(row, c, table.lang) or "—" for c in table.columns]
        lines.append("- " + " · ".join(cells))
    more = len(table.rows) - TELEGRAM_ROWS
    if more > 0:
        lines.append(t("export.table.more", table.lang, n=more))
    return "\n".join(lines)


@dataclass
class Made:
    export_id: str
    file_name: str
    rows: int
    truncated: bool
    empty_columns: list[str]
    card_refs: list[str] = field(default_factory=list)


@dataclass
class Shown:
    export_id: str
    rows: int
    shown: int
    truncated: bool
    empty_columns: list[str]
    card_refs: list[str]
    text: str | None


def _lang(conn: Connection, lang: str | None, channel: str) -> str:
    if lang is not None:
        return lang
    turn = attributed_turn(conn, channel)
    return turn["reply_language"] if turn else profile_locale(conn)


def _labels(conn: Connection) -> dict[str, dict[str, str]]:
    return {r.id: r.labels for r in conn.execute(T["categories"].select())}


def make(
    ctx: Ctx,
    *,
    columns: list[str],
    rows: list[dict[str, Any]],
    truncated: bool,
    fmt: FileFormat,
    title: str | None,
    lang: str | None,
    channel: str,
    via: str,
    tool: str | None = None,
    actor: str = "mona",
    conversation_id: str | None = None,
) -> Made:
    """Write the file under the exports folder, its `exports` row, the activity entry and card."""
    x = T["exports"]
    with ctx.engine.begin() as conn:
        lang = _lang(conn, lang, channel)
        shown = labelled(rows, _labels(conn), lang)
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
                at=ctx.clock(), actor=actor, via=via, action="export", subject_id=export_id,
                undoable=False,
                after={"format": fmt, "rows": len(rows), "file_name": name, "truncated": truncated},
            )
        )  # fmt: skip
        refs = (
            write_cards(conn, channel, tool, [("export", {"export_id": export_id})]) if tool else []
        )
        add_note(conn, conversation_id, "table.download", table_download(title, fmt, len(rows)))
    return Made(export_id, name, len(rows), truncated, empty_columns(columns, rows), refs)


def show(
    ctx: Ctx,
    *,
    columns: list[str],
    document_ids: list[str],
    rows: list[dict[str, Any]],
    truncated: bool,
    title: str | None,
    lang: str | None,
    channel: str,
    via: str,
    tool: str,
) -> Shown:
    """A36: the table's `exports` row with its spec (no file), the activity entry and card."""
    with ctx.engine.begin() as conn:
        lang = _lang(conn, lang, channel)
        title = (title or "").strip() or t("export.table.defaultTitle", lang)
        export_id = new_id("exp")
        conn.execute(
            insert(T["exports"]).values(
                id=export_id, status="ready", document_count=len(rows), format="table",
                title=title, truncated=truncated,
                spec={"columns": columns, "document_ids": document_ids, "lang": lang},
            )
        )  # fmt: skip
        conn.execute(
            insert(T["file_ops"]).values(
                at=ctx.clock(), actor="mona", via=via, action="export", subject_id=export_id,
                undoable=False,
                after={"format": "table", "rows": len(rows), "truncated": truncated},
            )
        )  # fmt: skip
        refs = write_cards(conn, channel, tool, [("table", {"export_id": export_id})])
        text = None
        if channel == "telegram":
            text = telegram_text(Table(title, columns, labelled(rows, _labels(conn), lang), lang))
    return Shown(
        export_id, len(rows), min(len(rows), SHOWN), truncated, empty_columns(columns, rows), refs,
        text,
    )  # fmt: skip

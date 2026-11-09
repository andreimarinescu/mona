"""C4 §3.11 `schedule_reminder`, §3.12 `draft_reply`, §3.13 `export_accountant_pack`, §3.17
`export_table` (A31)."""

from datetime import date
from typing import Annotated, Any, Literal

from pydantic import Field
from sqlalchemy import func, select

from mona.db import get_engine
from mona.db.models import Deadline, Document
from mona.mcp.core import Scope, ToolFailure, channel, clip, document_title, scope_for, tool
from mona.mcp.filters import (
    STATUSES,
    AmountParam,
    CategoryParam,
    CounterpartyParam,
    EntityParam,
    FiscalYearParam,
    HasDueDateParam,
    StatusParam,
    YearParam,
    document_clauses,
    ref,
    resolve_entity,
)
from mona.text import norm
from mona.workflow import deadlines, drafts, exports, tables
from mona.workflow.common import get_ctx
from mona.workflow.mcp import run, via


@tool(
    "Schedule a reminder for a deadline or a document on a given day; it appears in the morning "
    "brief that day. Offer it after mentioning a deadline; schedule it when the person agrees."
)
async def schedule_reminder(
    remind_on: date,
    deadline_id: Annotated[str | None, Field(pattern=r"^ddl_[0-9a-hjkmnp-tv-z]{26}$")] = None,
    document_id: Annotated[str | None, Field(pattern=r"^doc_[0-9a-hjkmnp-tv-z]{26}$")] = None,
    note: Annotated[str | None, Field(max_length=200)] = None,
) -> dict:
    ch = channel()
    out = await run(
        deadlines.add_reminder,
        get_ctx(),
        deadline_id=deadline_id,
        document_id=document_id,
        remind_on=remind_on,
        note=note,
        actor="mona",
        via=via(ch),
        channel=ch,
        tool="schedule_reminder",
    )
    return {
        "reminder_id": out.reminder_id,
        "remind_on": out.remind_on.isoformat(),
        "label": await _reminder_label(out.deadline_id, out.document_id),
        "deadline_id": out.deadline_id,
        "document_id": out.document_id,
        "created": out.created,
        "card_refs": out.card_refs,
    }


async def _reminder_label(deadline_id: str | None, document_id: str | None) -> str | None:
    if deadline_id is None:
        return await document_title(document_id)
    async with get_engine().connect() as conn:
        label = (
            await conn.execute(select(Deadline.label).where(Deadline.id == deadline_id))
        ).scalar()
    return clip(label)


@tool(
    "Draft a reply to a letter (for example asking the tax office for a payment schedule). The "
    "draft is written in the background and appears as a card the person can copy or download; "
    "you never send anything, and neither does the app. Unknown details stay as [BRACKETS]."
)
async def draft_reply(
    document_id: Annotated[str, Field(pattern=r"^doc_[0-9a-hjkmnp-tv-z]{26}$")],
    lang: Literal["en", "fr", "ro"] | None = None,
    instructions: Annotated[str | None, Field(max_length=500)] = None,
) -> dict:
    ch = channel()
    draft_id, refs = await run(
        drafts.start_draft,
        get_ctx(),
        document_id,
        lang=lang,
        instructions=instructions,
        channel=ch,
        tool="draft_reply",
    )
    return {
        "draft_id": draft_id,
        "status": "generating",
        "document_title": await document_title(document_id),
        "card_refs": refs,
    }


@tool(
    "Build the accountant pack for one company entity and fiscal year: a zip of its documents and "
    "a CSV index, written to the exports folder on this computer. It runs in the background and "
    "appears as a card; nothing is sent. Personal entities and Visitors can't be exported."
)
async def export_accountant_pack(
    entity: Annotated[str, Field(min_length=1, max_length=160)],
    fiscal_year: Annotated[int, Field(ge=2000, le=2100)],
) -> dict:
    ch = channel()
    async with get_engine().connect() as conn:
        try:
            found = await resolve_entity(await scope_for(conn, ch), entity)
        except ToolFailure:
            if ch == "web":
                raise
            try:
                found = await resolve_entity(Scope(conn, "web", frozenset()), entity)
            except ToolFailure:
                found = None
            if found is None:
                raise
    started = await run(
        exports.start_export,
        get_ctx(),
        found.id,
        fiscal_year,
        actor="mona",
        via=via(ch),
        channel=ch,
        tool="export_accountant_pack",
    )
    return {
        "export_id": started.export_id,
        "status": "building",
        "entity": ref(found.key, found.display_name),
        "fiscal_year": fiscal_year,
        "document_count": started.document_count,
        "card_refs": started.card_refs,
    }


DocIds = Annotated[
    list[Annotated[str, Field(pattern=r"^doc_[0-9a-hjkmnp-tv-z]{26}$")]],
    Field(min_length=1, max_length=tables.MAX_ROWS),
]


TABLE_CARD_NOTE = (
    "The person sees these rows as a table card under your reply. Don't write a table, a header "
    "row or any row values yourself; answer in one line and name any blank columns."
)


@tool(
    "Make a table of documents from a search or a list of documents, with the columns the person "
    "asks for. For a table the person wants to see, use format table; it appears in the chat. "
    "Make a file (csv, xlsx, docx) only when the person asks for a file, Excel, Word or CSV, or "
    "when rows exceeds shown. It takes the search_documents filters; has_due_date=true selects "
    "every payable (any document with a due date) in one call. A file appears as a card with a "
    "download; nothing is sent. When empty_columns is not empty, tell the person which columns "
    "came out blank. On Telegram, send the result's text as it is."
)
async def export_table(
    columns: Annotated[list[tables.Column], Field(min_length=1, max_length=10)],
    format: tables.Format,
    document_ids: DocIds | None = None,
    query: Annotated[str | None, Field(min_length=1, max_length=200)] = None,
    entity: EntityParam = None,
    category: CategoryParam = None,
    counterparty: CounterpartyParam = None,
    year: YearParam = None,
    fiscal_year: FiscalYearParam = None,
    date_from: date | None = None,
    date_to: date | None = None,
    amount_min: AmountParam = None,
    amount_max: AmountParam = None,
    has_due_date: HasDueDateParam = None,
    status: StatusParam = "any",
    title: Annotated[str | None, Field(max_length=80)] = None,
    lang: Literal["en", "fr", "ro"] | None = None,
) -> dict:
    filters = dict(
        entity=entity, category=category, counterparty=counterparty, year=year,
        fiscal_year=fiscal_year, date_from=date_from, date_to=date_to, amount_min=amount_min,
        amount_max=amount_max, has_due_date=has_due_date,
    )  # fmt: skip
    filtered = query is not None or status != "any" or any(v is not None for v in filters.values())
    if document_ids is not None and filtered:
        raise ToolFailure(
            "invalid_argument",
            "Pass either document_ids or filters, not both.",
            field="document_ids",
        )
    ch = channel()
    columns = list(dict.fromkeys(columns))
    async with get_engine().connect() as conn:
        scope = await scope_for(conn, ch)
        found = await _table_rows(scope, document_ids, query, filters, status)
    if not found:
        raise ToolFailure(
            "invalid_argument",
            "No document matches, so no table was made.",
            hint="Loosen the filters, or pass the document_ids from search_documents or "
            "list_deadlines.",
        )
    kept = found[: tables.MAX_ROWS]
    rows = [tables.row_values(r, ch) for r in kept]
    truncated = len(found) > tables.MAX_ROWS
    if format == "table":
        shown = await run(
            tables.show, get_ctx(), columns=columns, document_ids=[r.id for r in kept], rows=rows,
            truncated=truncated, title=title, lang=lang, channel=ch, via=via(ch),
            tool="export_table",
        )  # fmt: skip
        out = {
            "export_id": shown.export_id,
            "rows": shown.rows,
            "shown": shown.shown,
            "truncated": shown.truncated,
            "empty_columns": shown.empty_columns,
            "card_refs": shown.card_refs,
        }
        if shown.text is not None:
            out["text"] = shown.text
        else:
            out["note"] = TABLE_CARD_NOTE
        return out
    made = await run(
        tables.make, get_ctx(), columns=columns, rows=rows, truncated=truncated, fmt=format,
        title=title, lang=lang, channel=ch, via=via(ch), tool="export_table",
    )  # fmt: skip
    return {
        "export_id": made.export_id,
        "file_name": made.file_name,
        "rows": made.rows,
        "truncated": made.truncated,
        "empty_columns": made.empty_columns,
        "card_refs": made.card_refs,
    }


async def _table_rows(
    scope: Scope,
    document_ids: list[str] | None,
    query: str | None,
    filters: dict[str, Any],
    status: str,
) -> list[Any]:
    """C4 §2.6: only documents visible on the channel; at most `MAX_ROWS` + 1 to see the cut."""
    order: list[Any] = [Document.doc_date.desc().nulls_last(), Document.id]
    if document_ids is not None:
        clauses = [*scope.document_clauses(), Document.status.in_(STATUSES["any"])]
        clauses.append(Document.id.in_(list(dict.fromkeys(document_ids))))
    else:
        found = await document_clauses(scope, **filters, status=status)
        if found is None:
            return []
        clauses = found
        if query is not None:
            tsq = func.websearch_to_tsquery("mona", norm(query))
            clauses.append(Document.fts.op("@@")(tsq))
            order = [func.ts_rank(Document.fts, tsq).desc(), *order]
    stmt = tables.row_select(*clauses).order_by(*order).limit(tables.MAX_ROWS + 1)
    rows = list((await scope.conn.execute(stmt)).all())
    if document_ids is not None:
        at = {d: i for i, d in enumerate(dict.fromkeys(document_ids))}
        rows.sort(key=lambda r: at[r.id])
    return rows

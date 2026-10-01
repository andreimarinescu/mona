"""C4 §3.11 `schedule_reminder`, §3.12 `draft_reply`, §3.13 `export_accountant_pack`."""

from datetime import date
from typing import Annotated, Literal

from pydantic import Field

from mona.db import get_engine
from mona.mcp.core import Scope, ToolFailure, channel, scope_for, tool
from mona.mcp.filters import resolve_entity
from mona.workflow import deadlines, drafts, exports
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
        "deadline_id": out.deadline_id,
        "document_id": out.document_id,
        "created": out.created,
        "card_refs": out.card_refs,
    }


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
    return {"draft_id": draft_id, "status": "generating", "card_refs": refs}


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
        channel=ch,
        tool="export_accountant_pack",
    )
    return {
        "export_id": started.export_id,
        "status": "building",
        "document_count": started.document_count,
        "card_refs": started.card_refs,
    }

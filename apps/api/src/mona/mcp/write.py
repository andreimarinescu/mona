"""The write tools (C4 §3.5, §3.8, §3.9, §3.16): thin wrappers over `mona.services`.

The actor is always `mona` (D5); `via` follows the channel."""

from datetime import date
from typing import Annotated, Any, Literal

import anyio.to_thread
from pydantic import Field
from sqlalchemy import select

from mona.api.deps import get_ctx
from mona.db import get_engine
from mona.db.models import Document, FileOp, OpGroup, Rule
from mona.dto import RulePreview
from mona.fileops import FileOpError
from mona.mcp.core import (
    Scope,
    ToolFailure,
    channel,
    clip,
    document_title,
    not_found,
    scope_for,
    tool,
    write_cards,
)
from mona.mcp.filters import CategoryParam, EntityParam, resolve_entity
from mona.mcp.read import DocIdParam
from mona.services import apply_rule as apply_service
from mona.services import correct_document as correct_service
from mona.services import preview_rule as preview_service
from mona.services import undo as undo_service
from mona.services.rules import Visible
from mona.visibility import rule_visibility

RuleIdParam = Annotated[str, Field(pattern=r"^rul_[0-9a-hjkmnp-tv-z]{26}$")]
GroupIdParam = Annotated[str, Field(pattern=r"^grp_[0-9a-hjkmnp-tv-z]{26}$")]
Name = Annotated[str, Field(min_length=1, max_length=160)]
TOOL_MOVES = 5
CODES = ("invalid_argument", "not_found", "forbidden_path", "not_allowed", "conflict")
SKIP_STATES = {"undone": "already_undone"}


def via(scope: Scope) -> str:
    return "chat" if scope.channel == "web" else "telegram"


def candidate_filter(scope: Scope) -> Visible:
    """C4 §2.6 for rule candidates: off the web, invisible documents are never listed or moved."""
    return None if scope.channel == "web" else scope.document_visible


async def call_service(fn: Any, *args: Any, **kwargs: Any) -> Any:
    """A sync service off the loop; its C4 §2.4 errors become tool errors."""
    try:
        return await anyio.to_thread.run_sync(lambda: fn(*args, **kwargs))
    except FileOpError as err:
        code = err.code if err.code in CODES else "conflict"
        hint = err.hint if code != "conflict" else (err.hint or err.code)
        raise ToolFailure(
            code, err.message, hint=hint, field=getattr(err, "field", None),
            valid=getattr(err, "valid", None),
        ) from None  # fmt: skip


async def visible_document(scope: Scope, document_id: str) -> None:
    found = (
        await scope.conn.execute(
            select(Document.id).where(Document.id == document_id, *scope.document_clauses())
        )
    ).first()
    if found is None:
        raise not_found("document")


async def visible_rule(scope: Scope, rule_id: str) -> Any:
    row = (
        await scope.conn.execute(
            select(Rule.id, Rule.conditions, Rule.action).where(Rule.id == rule_id)
        )
    ).first()
    seen = await rule_visibility(scope)
    if row is None or (seen is not None and not seen.visible(row.conditions, row.action)):
        raise not_found("rule")
    return row


async def visible_entries(scope: Scope, entries: list[Any], rule_id: str | None) -> bool:
    """C4 §2.6: an entry or group is invisible when any of its documents or its rule is."""
    if scope.channel == "web":
        return True
    docs = {e.document_id for e in entries if e.document_id}
    if docs:
        shown = (
            await scope.conn.execute(
                select(Document.id).where(Document.id.in_(docs), *scope.document_clauses())
            )
        ).scalars()
        if set(shown) != docs:
            return False
    seen = await rule_visibility(scope)
    rules = {r for r in (rule_id, *(e.rule_id for e in entries)) if r}
    if seen is not None and rules:
        rows = (
            await scope.conn.execute(select(Rule.conditions, Rule.action).where(Rule.id.in_(rules)))
        ).all()
        if not all(seen.visible(r.conditions, r.action) for r in rows):
            return False
    return True


def path_of(segments: list[str], name: str) -> str:
    return "/".join([*segments, name])


def preview_result(p: RulePreview) -> dict[str, Any]:
    """C4 §3.8's result from the C1 §11.5 `RulePreview`; `moves` capped at 5."""
    r = p.rule
    return {
        "rule_id": r.id,
        "name": clip(r.name),
        "state": r.state,
        "condition_text": clip(r.condition_text, 400),
        "moves_total": p.moves_total,
        "stays_total": p.stays_total,
        "moves": [
            {
                "document_id": m.document_id,
                "title": clip(m.title),
                "from": clip(path_of(m.from_, m.from_file_name), 400),
                "to": clip(path_of(m.to, m.to_file_name), 400),
            }
            for m in p.moves[:TOOL_MOVES]
        ],
    }


@tool(
    "Apply a correction the person has stated for one document (entity, category, subcategory, "
    "counterparty or a field value), then re-file it with its new name. Use it only for a "
    "correction the person gave you, not to change your own mind. With scope 'all', also "
    "prepare a rule for every document from the same counterparty and show its preview; the "
    "rule is not active until applied."
)
async def correct_document(
    document_id: DocIdParam,
    entity: EntityParam = None,
    sub_unit: Annotated[str | None, Field(min_length=1, max_length=120)] = None,
    category: CategoryParam = None,
    subcategory: Annotated[str | None, Field(min_length=1, max_length=120)] = None,
    counterparty: Annotated[str | None, Field(min_length=1, max_length=160)] = None,
    doc_date: date | None = None,
    period_end: date | None = None,
    due_date: date | None = None,
    amount: Annotated[float | None, Field(ge=0)] = None,
    currency: Literal["EUR", "RON"] | None = None,
    scope: Literal["one", "all"] = "one",
) -> dict:
    async with get_engine().begin() as conn:
        s = await scope_for(conn, channel())
        await visible_document(s, document_id)
        entity_key = (await resolve_entity(s, entity)).key if entity is not None else None
    result = await call_service(
        correct_service, get_ctx(), document_id, actor="mona", via=via(s), entity=entity_key,
        sub_unit=sub_unit, category=category, subcategory=subcategory, counterparty=counterparty,
        doc_date=doc_date, period_end=period_end, due_date=due_date, amount=amount,
        currency=currency, scope=scope,
    )  # fmt: skip
    doc = result.document
    preview, keep = result.preview, candidate_filter(s)
    if preview is not None and keep is not None:
        preview = await call_service(preview_service, get_ctx(), result.rule.id, visible=keep)
    out: dict[str, Any] = {
        "document_id": document_id,
        "title": await document_title(document_id),
        "outcome": result.outcome,
        "path": clip(path_of(doc.path, doc.file_name), 400),
        "journal_ids": result.journal_ids,
        "group_id": result.group_id,
        "rule": {"id": result.rule.id, "state": result.rule.state} if result.rule else None,
        "preview": preview_result(preview) if preview else None,
    }
    if result.rule is not None:
        cards = [("rulePreview", {"rule_id": result.rule.id})]
    else:
        cards = [("doc", {"document_id": document_id})]
    async with get_engine().begin() as conn:
        s = await scope_for(conn, channel())
        out["card_refs"] = await write_cards(s, "correct_document", cards)
    return out


@tool(
    "Show what a rule would move: how many documents would move, how many already match, and a "
    "few before → after paths. Use it before apply_rule when the person hasn't seen a preview "
    "yet."
)
async def preview_rule(rule_id: RuleIdParam) -> dict:
    async with get_engine().begin() as conn:
        s = await scope_for(conn, channel())
        await visible_rule(s, rule_id)
        preview = await call_service(
            preview_service, get_ctx(), rule_id, visible=candidate_filter(s)
        )
        out = preview_result(preview)
        out["card_refs"] = await write_cards(
            s, "preview_rule", [("rulePreview", {"rule_id": rule_id})]
        )
    return out


@tool(
    "Activate a rule and re-file the documents it matches, as shown by its preview. Every move "
    "is journaled and the whole application can be undone in one step. Use it only after the "
    "person has agreed to the preview."
)
async def apply_rule(rule_id: RuleIdParam) -> dict:
    async with get_engine().begin() as conn:
        s = await scope_for(conn, channel())
        await visible_rule(s, rule_id)
    applied = await call_service(
        apply_service, get_ctx(), rule_id, actor="mona", via=via(s), visible=candidate_filter(s)
    )
    async with get_engine().begin() as conn:
        s = await scope_for(conn, channel())
        refs = await write_cards(s, "apply_rule", [("rulePreview", {"rule_id": rule_id})])
    return {
        "rule_id": rule_id,
        "name": clip(applied.preview.rule.name) if applied.preview else None,
        "group_id": applied.group_id,
        "moved": applied.moved,
        "unchanged": applied.unchanged,
        "failed": [{"document_id": f["document_id"], "code": f["code"]} for f in applied.failed],
        "card_refs": refs,
    }


@tool(
    "Undo one journal entry or a whole group (a batch, a rule application) when the person asks "
    "you to. Entries that were changed again since are skipped and reported. Undoing an undo "
    "redoes it. Say exactly what was undone."
)
async def undo(
    journal_id: Annotated[int | None, Field(ge=1)] = None,
    group_id: GroupIdParam | None = None,
) -> dict:
    if (journal_id is None) == (group_id is None):
        raise ToolFailure(
            "invalid_argument", "Pass exactly one of journal_id or group_id.", field="journal_id"
        )
    async with get_engine().begin() as conn:
        s = await scope_for(conn, channel())
        if journal_id is not None:
            entries = (
                await conn.execute(
                    select(FileOp.document_id, FileOp.rule_id).where(
                        FileOp.id == journal_id, FileOp.fs_state == "done"
                    )
                )
            ).all()
            group_rule = None
        else:
            group_rule = (
                await conn.execute(select(OpGroup.rule_id).where(OpGroup.id == group_id))
            ).first()
            if group_rule is None:
                raise not_found("group")
            entries = (
                await conn.execute(
                    select(FileOp.document_id, FileOp.rule_id).where(
                        FileOp.group_id == group_id, FileOp.fs_state == "done"
                    )
                )
            ).all()
        if (journal_id is not None and not entries) or not await visible_entries(
            s, entries, group_rule.rule_id if group_rule else None
        ):
            raise not_found("journal entry" if journal_id is not None else "group")
    result = await call_service(
        undo_service, get_ctx(), actor="mona", via=via(s), journal_id=journal_id,
        group_id=group_id,
    )  # fmt: skip
    skipped = [
        {"journal_id": x["journal_id"], "state": SKIP_STATES.get(x["state"], x["state"])}
        for x in result.skipped
        if x["journal_id"] is not None
    ]
    if journal_id is not None and skipped and skipped[0]["state"] == "not_allowed":
        raise ToolFailure("not_allowed", "Mona can't move a document to the trash.")
    return {
        "group_id": result.group_id,
        "undone": [
            {
                "journal_id": u["journal_id"],
                "document_id": u["document_id"],
                "title": clip(u["title"]),
                "to": clip(u["to"], 400),
            }
            for u in result.undone
        ],  # fmt: skip
        "skipped": skipped,
    }

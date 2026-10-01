"""C2 §7 rules: list, detail, patch, preview, apply, learned."""

import re
from datetime import datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query
from pydantic import ValidationError
from sqlalchemy import Connection, case, func, select

from mona import clock
from mona.api import cardnotes, views
from mona.api.deps import CtxDep, Lang, Offset, Page, PageLimit, body_id, path_id, run
from mona.api.errors import ApiFailure, camel_path, errors
from mona.api.models import ApplyResult, ConversationRef, LearnedItem, RuleListItem, RulePatch
from mona.db import get_sync_engine
from mona.dto import RulePreview
from mona.fileops import group_state
from mona.rules import store
from mona.rules.grammar import RuleBody, unresolved
from mona.services import Ctx, apply_rule, preview_rule, registry
from mona.services.dto import rule as rule_dto
from mona.services.registry import T
from mona.text import norm

router = APIRouter(prefix="/api/rules", tags=["rules"])

RuleId = path_id("rul", "id")
STATE_ORDER = case({"active": 0, "draft": 1, "disabled": 2}, value=T["rules"].c.state)
_PROBLEM_FIELD = re.compile(r"^(conditions)\[(\d+)\]|^(action\.\w+)")


def _item(conn: Connection, row: Any, lang: str) -> dict[str, Any]:
    return views.rule_item(registry.load(conn), row, lang, store.registry(conn))


def _list(p: dict[str, Any], lang: str) -> dict[str, Any]:
    r = T["rules"]
    with get_sync_engine().connect() as conn:
        rows = conn.execute(
            select(r).order_by(STATE_ORDER, r.c.priority.desc(), r.c.key)
        ).mappings()
        snap = registry.load(conn)
        entity_key = snap.entity_keys.get(p["entity_id"]) if p["entity_id"] else None
        wanted = norm(p["q"]) if p["q"] else None
        matches = [
            x
            for x in rows
            if (p["state"] is None or x["state"] == p["state"])
            and (p["source"] is None or x["source"] == p["source"])
            and (p["entity_id"] is None or x["action"].get("entity") == entity_key)
            and (wanted is None or wanted in norm(x["name"]))
        ]
        reg = store.registry(conn)
        page = matches[p["offset"] : p["offset"] + p["limit"]]
        items = [views.rule_item(snap, x, lang, reg) for x in page]
    return {"items": items, "total": len(matches), "offset": p["offset"], "limit": p["limit"]}


@router.get(
    "", operation_id="listRules", response_model=Page[RuleListItem],
    responses=errors(400, 401, 423),
)  # fmt: skip
async def list_rules(
    lang: Lang,
    state: Literal["draft", "active", "disabled"] | None = None,
    source: Literal["seed", "interview", "correction"] | None = None,
    entityId: str | None = None,  # noqa: N803
    q: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    offset: Offset = 0,
    limit: PageLimit = 50,
) -> dict[str, Any]:
    body_id(entityId, "ent", "entityId")
    params = {"state": state, "source": source, "entity_id": entityId, "q": q,
              "offset": offset, "limit": limit}  # fmt: skip
    return await run(_list, params, lang)


def _learned(since: datetime, lang: str) -> list[dict[str, Any]]:
    r, g, f = T["rules"], T["op_groups"], T["file_ops"]
    with get_sync_engine().connect() as conn:
        rows = conn.execute(
            select(r)
            .where(r.c.created_at >= since, r.c.source.in_(("interview", "correction")))
            .order_by(r.c.created_at.desc(), r.c.id.desc())
        ).mappings()
        snap = registry.load(conn)
        out = []
        for row in rows:
            groups = conn.execute(
                select(g.c.id).where(g.c.rule_id == row["id"], g.c.kind == "rule_apply")
            ).scalars()
            live = [gid for gid in groups if group_state(conn, gid)[0] != "undone"]
            moved = 0
            if live:
                moved = conn.execute(
                    select(func.count()).where(
                        f.c.group_id.in_(live),
                        f.c.fs_state == "done",
                        f.c.action.in_(("file", "move", "rename")),
                    )
                ).scalar_one()
            out.append(
                LearnedItem(
                    rule=rule_dto(snap, row, lang), created_at=row["created_at"], moved=moved
                ).model_dump(mode="json")
            )
    return out


@router.get(
    "/learned", operation_id="listLearnedRules", response_model=list[LearnedItem],
    responses=errors(400, 401, 423),
)  # fmt: skip
async def learned(lang: Lang, since: datetime | None = None) -> list[dict[str, Any]]:
    since = since or clock.now() - timedelta(days=7)
    return await run(_learned, since, lang)


def _get(rule_id: str, lang: str) -> dict[str, Any]:
    with get_sync_engine().connect() as conn:
        row = store.rule_row(conn, rule_id)
        if row is None:
            raise ApiFailure(404, "not_found", "No rule with that id.")
        return _item(conn, row, lang)


@router.get(
    "/{id}", operation_id="getRule", response_model=RuleListItem,
    responses=errors(401, 404, 423),
)  # fmt: skip
async def get_rule(rule_id: RuleId, lang: Lang) -> dict[str, Any]:
    return await run(_get, rule_id, lang)


def _invalid_rule(message: str, field: str | None) -> ApiFailure:
    return ApiFailure(
        422, "invalid_rule", "The rule is invalid.", field=field, details={"message": message}
    )


def _problem_field(problem: str) -> str | None:
    m = _PROBLEM_FIELD.match(problem)
    if not m:
        return None
    return f"conditions.{m.group(2)}" if m.group(1) else m.group(3)


def _patch(ctx: Ctx, rule_id: str, body: RulePatch, lang: str) -> dict[str, Any]:
    given = body.model_fields_set
    now = clock.now()
    with get_sync_engine().begin() as conn:
        before = store.rule_row(conn, rule_id)
        if before is None:
            raise ApiFailure(404, "not_found", "No rule with that id.")
        raw = {
            "conditions": body.conditions if "conditions" in given else before["conditions"],
            "action": body.action if "action" in given else before["action"],
        }
        try:
            rule_body = RuleBody.model_validate(raw)
        except ValidationError as e:
            err = e.errors()[0]
            raise _invalid_rule(str(err.get("msg", "invalid")), camel_path(err["loc"])) from None
        problems = unresolved(rule_body, store.registry(conn))
        if problems:
            raise _invalid_rule(problems[0], _problem_field(problems[0]))
        state = before["state"]
        if "enabled" in given and body.enabled is not None:
            state = "active" if body.enabled else "disabled"
        priority = body.priority if "priority" in given and body.priority is not None else None
        after, outcome = store.save_rule(
            conn, key=before["key"], name=body.name if body.name else before["name"],
            state=state, source=before["source"], body=rule_body,
            priority=priority if priority is not None else before["priority"],
            names=store.names(conn),
        )  # fmt: skip
        if outcome != "unchanged":
            store.journal_rule(conn, "rule.change", before, after, actor="user", via="ui", at=now)
    if outcome != "unchanged":
        with get_sync_engine().connect() as conn:
            store.write_export(conn, ctx.config_dir, now=now)
    with get_sync_engine().connect() as conn:
        return _item(conn, store.rule_row(conn, rule_id), lang)


@router.patch(
    "/{id}", operation_id="patchRule", response_model=RuleListItem,
    responses=errors(400, 401, 403, 404, 415, 422, 423),
)  # fmt: skip
async def patch_rule(rule_id: RuleId, body: RulePatch, ctx: CtxDep, lang: Lang) -> dict[str, Any]:
    return await run(_patch, ctx, rule_id, body, lang)


def capped(preview: RulePreview, limit: int) -> dict[str, Any]:
    out = preview.model_dump(mode="json")
    out["moves"] = out["moves"][:limit]
    return out


def _preview(ctx: Ctx, rule_id: str, limit: int, lang: str) -> dict[str, Any]:
    with get_sync_engine().connect() as conn:
        if store.rule_row(conn, rule_id) is None:
            raise ApiFailure(404, "not_found", "No rule with that id.")
    return capped(preview_rule(ctx, rule_id, lang=lang), limit)


@router.get(
    "/{id}/preview", operation_id="previewRule", response_model=RulePreview,
    responses=errors(400, 401, 404, 423),
)  # fmt: skip
async def rule_preview(
    rule_id: RuleId, ctx: CtxDep, lang: Lang,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict[str, Any]:  # fmt: skip
    return await run(_preview, ctx, rule_id, limit, lang)


def _apply(ctx: Ctx, rule_id: str, conversation_id: str | None, lang: str) -> dict[str, Any]:
    with get_sync_engine().connect() as conn:
        row = store.rule_row(conn, rule_id)
    if row is None:
        raise ApiFailure(404, "not_found", "No rule with that id.")
    result = apply_rule(ctx, rule_id, actor="user", via="ui", lang=lang)
    if conversation_id is not None:
        with get_sync_engine().begin() as conn:
            if cardnotes.conversation_exists(conn, conversation_id):
                text = cardnotes.rule_apply_text(row["name"], result.moved, result.unchanged)
                cardnotes.write(conn, conversation_id, "rule.apply", text)
    return {
        "preview": capped(result.preview, 200),  # type: ignore[arg-type]
        "group_id": result.group_id,
        "moved": result.moved,
        "unchanged": result.unchanged,
        "failed": result.failed,
    }


@router.post(
    "/{id}/apply", operation_id="applyRule", response_model=ApplyResult,
    responses=errors(400, 401, 403, 404, 409, 415, 423),
)  # fmt: skip
async def rule_apply(
    rule_id: RuleId, ctx: CtxDep, lang: Lang, body: ConversationRef | None = None
) -> dict[str, Any]:
    conversation_id = body_id(body.conversation_id, "cnv", "conversationId") if body else None
    return await run(_apply, ctx, rule_id, conversation_id, lang)

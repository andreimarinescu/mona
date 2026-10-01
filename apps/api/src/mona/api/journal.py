"""C2 §9 journal and activity: reading, undo and redo, with §14 notes."""

from collections.abc import Iterable
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import Connection, Text, and_, cast, exists, func, literal, or_, select, union_all

from mona.api import cardnotes
from mona.api.deps import CtxDep, FeedLimit, body_id, decode_cursor, encode_cursor, path_id, run
from mona.api.errors import ApiFailure, errors
from mona.api.models import ActivityPage, ConversationRef, EntryDetail, GroupDetail, UndoResult
from mona.db import get_sync_engine
from mona.services import Ctx
from mona.services import undo as undo_service
from mona.services.dto import journal_entry, journal_group
from mona.services.registry import T
from mona.text import norm

router = APIRouter(prefix="/api", tags=["journal"])

GroupId = path_id("grp", "id")
PREVIEW = 5
GROUP_LABELS = {
    "intake_batch": "the intake batch",
    "rule_apply": "a rule application",
    "correction": "a correction",
    "undo": "an undo",
    "redo": "a redo",
    "refile": "a re-filing",
}


def journal_id_param(value: Annotated[str, Path(alias="id")]) -> int:
    if not value.isdigit() or int(value) < 1:
        raise ApiFailure(404, "not_found", "No journal entry with that id.")
    return int(value)


JournalId = Annotated[int, Depends(journal_id_param)]


def doc_refs(conn: Connection, ids: Iterable[str]) -> dict[str, dict[str, Any]]:
    ids = sorted({i for i in ids if i})
    if not ids:
        return {}
    d = T["documents"]
    rows = conn.execute(
        select(d.c.id, d.c.title, d.c.original_name, d.c.current_path, d.c.deleted_at).where(
            d.c.id.in_(ids)
        )
    ).all()
    return {
        r.id: {
            "title": r.title or r.original_name,
            "file_name": r.current_path.rpartition("/")[2],
            "deleted": r.deleted_at is not None,
        }
        for r in rows
    }


def rule_names(conn: Connection, ids: Iterable[str | None]) -> dict[str, dict[str, str]]:
    ids = sorted({i for i in ids if i})
    if not ids:
        return {}
    r = T["rules"]
    return {
        i: {"name": n} for i, n in conn.execute(select(r.c.id, r.c.name).where(r.c.id.in_(ids)))
    }


def redo_group(conn: Connection, group_id: str) -> str | None:
    """The live undo (or redo) group targeting this one (C7 §5.4), for "Redo"."""
    from mona.fileops import group_state

    g = T["op_groups"]
    for gid in conn.execute(
        select(g.c.id)
        .where(g.c.target_group_id == group_id)
        .order_by(g.c.created_at.desc(), g.c.id.desc())
    ).scalars():
        if group_state(conn, gid)[0] != "undone":
            return gid
    return None


def _items() -> Any:
    """Groups with a done entry, and done entries with no group (C2 §9.1)."""
    g, f = T["op_groups"], T["file_ops"]
    entry = f.alias("entry")
    groups = select(
        literal("g").label("k"), g.c.id.label("ref"), g.c.created_at.label("ts"),
        g.c.actor.label("actor"), g.c.kind.label("what"),
    ).where(exists().where(f.c.group_id == g.c.id, f.c.fs_state == "done"))  # fmt: skip
    entries = select(
        literal("e").label("k"), cast(entry.c.id, Text).label("ref"), entry.c.at.label("ts"),
        entry.c.actor.label("actor"), entry.c.action.label("what"),
    ).where(entry.c.group_id.is_(None), entry.c.fs_state == "done")  # fmt: skip
    return union_all(groups, entries).subquery("items")


def _filters(p: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in p.items() if k not in ("cursor", "limit")}


def activity_page(p: dict[str, Any]) -> dict[str, Any]:
    after = decode_cursor(p["cursor"], _filters(p))
    sub = _items()
    key = sub.c.k + sub.c.ref
    stmt = select(sub.c.k, sub.c.ref, sub.c.ts)
    if p["actor"]:
        stmt = stmt.where(sub.c.actor == p["actor"])
    if p["kind"]:
        stmt = stmt.where(sub.c.what == p["kind"])
    f, d = T["file_ops"], T["documents"]
    conds = []
    if p["entity_id"]:
        conds.append(d.c.entity_id == p["entity_id"])
    if p["q"]:
        haystack = func.lower(
            func.unaccent(func.coalesce(d.c.title, d.c.original_name) + " " + d.c.current_path)
        )
        conds.append(haystack.contains(norm(p["q"]), autoescape=True))
    if conds:
        own = or_(
            and_(sub.c.k == "g", f.c.group_id == sub.c.ref),
            and_(sub.c.k == "e", cast(f.c.id, Text) == sub.c.ref),
        )
        stmt = stmt.where(
            exists().where(d.c.id == f.c.document_id, f.c.fs_state == "done", own, *conds)
        )
    if after is not None:
        at = datetime.fromisoformat(after[0])
        stmt = stmt.where(or_(sub.c.ts < at, and_(sub.c.ts == at, key < after[1])))
    stmt = stmt.order_by(sub.c.ts.desc(), key.desc()).limit(p["limit"] + 1)
    with get_sync_engine().connect() as conn:
        rows = conn.execute(stmt).all()
        more = len(rows) > p["limit"]
        rows = rows[: p["limit"]]
        out = build_items(conn, rows)
    next_cursor = None
    if more and rows:
        last = rows[-1]
        next_cursor = encode_cursor([last.ts.isoformat(), last.k + last.ref], _filters(p))
    return {**out, "next_cursor": next_cursor}


def build_items(conn: Connection, rows: list[Any]) -> dict[str, Any]:
    """`ActivityItem`s for (kind, ref) rows plus their `documents` and `rules` maps."""
    f = T["file_ops"]
    items: list[dict[str, Any]] = []
    doc_ids: list[str] = []
    rule_ids: list[str | None] = []
    for row in rows:
        if row.k == "g":
            group = journal_group(conn, row.ref)
            entries = (
                conn.execute(
                    select(f)
                    .where(f.c.group_id == row.ref, f.c.fs_state == "done")
                    .order_by(f.c.id)
                )
                .mappings()
                .all()
            )
            preview = [journal_entry(conn, e) for e in entries[:PREVIEW]]
            doc_ids += [e["document_id"] for e in entries[:PREVIEW]]
            rule_ids += [group.rule_id, *(e["rule_id"] for e in entries[:PREVIEW])]
            items.append(
                {
                    "kind": "group",
                    "group": group.model_dump(mode="json"),
                    "preview": [e.model_dump(mode="json") for e in preview],
                    "entries_total": len(entries),
                    "redo_group_id": redo_group(conn, row.ref),
                }
            )
        else:
            e = conn.execute(select(f).where(f.c.id == int(row.ref))).mappings().one()
            doc_ids.append(e["document_id"])
            rule_ids.append(e["rule_id"])
            items.append({"kind": "entry", "entry": journal_entry(conn, e).model_dump(mode="json")})
    return {
        "items": items,
        "documents": doc_refs(conn, doc_ids),
        "rules": rule_names(conn, rule_ids),
    }


@router.get(
    "/activity", operation_id="listActivity", response_model=ActivityPage,
    responses=errors(400, 401, 423),
)  # fmt: skip
async def activity(
    actor: Literal["mona", "user"] | None = None,
    entityId: str | None = None,  # noqa: N803
    kind: Annotated[str | None, Query(max_length=40)] = None,
    q: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    cursor: Annotated[str | None, Query(max_length=400)] = None,
    limit: FeedLimit = 30,
) -> dict[str, Any]:
    body_id(entityId, "ent", "entityId")
    params = {"actor": actor, "entity_id": entityId, "kind": kind, "q": q, "cursor": cursor,
              "limit": limit}  # fmt: skip
    return await run(activity_page, params)


def _group(group_id: str) -> dict[str, Any]:
    g, f = T["op_groups"], T["file_ops"]
    with get_sync_engine().connect() as conn:
        if conn.execute(select(g.c.id).where(g.c.id == group_id)).first() is None:
            raise ApiFailure(404, "not_found", "No journal group with that id.")
        entries = (
            conn.execute(
                select(f).where(f.c.group_id == group_id, f.c.fs_state == "done").order_by(f.c.id)
            )
            .mappings()
            .all()
        )
        return {
            "group": journal_group(conn, group_id).model_dump(mode="json"),
            "entries": [journal_entry(conn, e).model_dump(mode="json") for e in entries],
            "documents": doc_refs(conn, (e["document_id"] for e in entries)),
        }


@router.get(
    "/journal/groups/{id}", operation_id="getJournalGroup", response_model=GroupDetail,
    responses=errors(401, 404, 423),
)  # fmt: skip
async def get_group(group_id: GroupId) -> dict[str, Any]:
    return await run(_group, group_id)


def _entry(entry_id: int) -> dict[str, Any]:
    f = T["file_ops"]
    with get_sync_engine().connect() as conn:
        e = (
            conn.execute(select(f).where(f.c.id == entry_id, f.c.fs_state == "done"))
            .mappings()
            .first()
        )
        if e is None:
            raise ApiFailure(404, "not_found", "No journal entry with that id.")
        return {
            "entry": journal_entry(conn, e).model_dump(mode="json"),
            "documents": doc_refs(conn, [e["document_id"]]),
        }


@router.get(
    "/journal/{id}", operation_id="getJournalEntry", response_model=EntryDetail,
    responses=errors(401, 404, 423),
)  # fmt: skip
async def get_entry(entry_id: JournalId) -> dict[str, Any]:
    return await run(_entry, entry_id)


SKIP_STATES = {"undone": "already_undone"}
SINGLE_ERRORS = {
    "superseded": (409, "superseded", "The document has moved since; this can't be undone."),
    "already_undone": (409, "already_undone", "The change has already been undone."),
    "not_undoable": (422, "not_undoable", "This change can't be undone."),
    "not_allowed": (403, "not_allowed", "This change can't be undone here."),
}


def _undo_result(ctx: Ctx, result: Any) -> dict[str, Any]:
    f = T["file_ops"]
    new_ids = [u["entry_id"] for u in result.undone if u.get("entry_id")]
    with ctx.engine.connect() as conn:
        entries = [
            journal_entry(conn, e)
            for e in conn.execute(select(f).where(f.c.id.in_(new_ids)).order_by(f.c.id)).mappings()
        ] if new_ids else []  # fmt: skip
    after = {e.id: e for e in entries}
    undone = []
    for u in result.undone:
        entry = after.get(u["entry_id"])
        to = entry.after if entry is not None else None
        undone.append(
            {
                "journal_id": u["journal_id"],
                "document_id": u["document_id"],
                "title": u["title"],
                "to": to.model_dump(mode="json") if to else None,
            }
        )
    return {
        "group_id": result.group_id,
        "undone": undone,
        "skipped": [
            {**s, "state": SKIP_STATES.get(s["state"], s["state"])}
            for s in result.skipped
            if s["journal_id"] is not None
        ],
        "entries": [e.model_dump(mode="json") for e in entries],
        "rule_states": [dict(r) for r in result.rule_states],
    }


def _raise_for(state: str) -> None:
    state = SKIP_STATES.get(state, state)
    status, code, message = SINGLE_ERRORS.get(state, SINGLE_ERRORS["not_undoable"])
    raise ApiFailure(status, code, message)


def _undo_entry(ctx: Ctx, entry_id: int, conversation_id: str | None) -> dict[str, Any]:
    with cardnotes.undo_note(conversation_id):
        result = undo_service(ctx, actor="user", via="ui", journal_id=entry_id)
    if not result.undone:
        _raise_for(result.skipped[0]["state"] if result.skipped else "not_undoable")
    return _undo_result(ctx, result)


@router.post(
    "/journal/{id}/undo", operation_id="undoJournalEntry", response_model=UndoResult,
    responses=errors(400, 401, 403, 404, 409, 415, 422, 423),
)  # fmt: skip
async def undo_entry(
    entry_id: JournalId, ctx: CtxDep, body: ConversationRef | None = None
) -> dict[str, Any]:
    conversation_id = body_id(body.conversation_id, "cnv", "conversationId") if body else None
    return await run(_undo_entry, ctx, entry_id, conversation_id)


def _undo_group(ctx: Ctx, group_id: str, conversation_id: str | None) -> dict[str, Any]:
    g = T["op_groups"]
    with ctx.engine.connect() as conn:
        kind = conn.execute(select(g.c.kind).where(g.c.id == group_id)).scalar()
    if kind is None:
        raise ApiFailure(404, "not_found", "No journal group with that id.")
    result = undo_service(ctx, actor="user", via="ui", group_id=group_id)
    if result.group_id is None:
        states = [s["state"] for s in result.skipped]
        _raise_for(states[-1] if states else "not_undoable")
    if conversation_id is not None and result.undone:
        with ctx.engine.begin() as conn:
            if cardnotes.conversation_exists(conn, conversation_id):
                summary = GROUP_LABELS.get(kind, "a group of changes")
                text_ = cardnotes.undo_group_text(len(result.undone), summary)
                cardnotes.write(conn, conversation_id, "undo", text_)
    return _undo_result(ctx, result)


@router.post(
    "/journal/groups/{id}/undo", operation_id="undoJournalGroup", response_model=UndoResult,
    responses=errors(400, 401, 403, 404, 409, 415, 422, 423),
)  # fmt: skip
async def undo_group(
    group_id: GroupId, ctx: CtxDep, body: ConversationRef | None = None
) -> dict[str, Any]:
    conversation_id = body_id(body.conversation_id, "cnv", "conversationId") if body else None
    return await run(_undo_group, ctx, group_id, conversation_id)

"""`preview_rule` / `apply_rule` (C4 §3.8/§3.9, C1 §11.5) and rules drafted from corrections."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, insert, select

from mona.dto import RulePreview
from mona.dto.models import RuleMove
from mona.fileops import Change, FileOpError, group_state, is_suffix_of
from mona.fileops.ops import error_code
from mona.ids import new_id
from mona.rules import store
from mona.rules.engine import learned_priority
from mona.rules.grammar import RuleBody, unresolved
from mona.rules.scoring import score, tokens_used
from mona.services import registry
from mona.services.context import Ctx
from mona.services.dto import rule as rule_dto
from mona.services.dto import split
from mona.services.errors import ServiceError
from mona.services.placement import Candidate, rule_candidates, subject
from mona.services.registry import Snapshot, T


def draft_from_correction(
    conn: Connection,
    snap: Snapshot,
    doc: Mapping[str, Any],
    *,
    entity: str | None,
    unit: str | None,
    category: str | None,
    subcategory: str | None,
    counterparty_id: str | None,
    actor: str,
    via: str,
    at: datetime,
    group_id: str | None,
    textcache: Path,
) -> tuple[Mapping[str, Any], int | None]:
    """C4 §3.5.4: a draft `counterparty equals <key>` rule above the rules it corrects."""
    cp_key = snap.counterparty_keys.get(counterparty_id)
    if cp_key is None:
        raise ServiceError("invalid_argument", "A rule for every document like this needs a "
                           "counterparty.", field="scope")  # fmt: skip
    action = {"entity": entity, "unit": unit, "category": category, "subcategory": subcategory}
    body = RuleBody.model_validate(
        {
            "conditions": [{"field": "counterparty", "op": "equals", "value": cp_key}],
            "action": {k: v for k, v in action.items() if v is not None},
        }
    )
    problems = unresolved(body, store.registry(conn))
    if problems:
        raise ServiceError("invalid_argument", problems[0], field="scope")
    conditions = [c.model_dump() for c in body.conditions]
    t = T["rules"]
    for r in conn.execute(
        select(t).where(t.c.state == "draft", t.c.source == "correction")
    ).mappings():
        if r["conditions"] == conditions and r["action"] == body.action.model_dump():
            return r, None
    specs = registry.rule_specs(conn)
    s = subject(conn, snap, doc, textcache)
    matched = [r.priority for r in specs if r.state == "active" and r.matches(s, snap.world)]
    cp_name = snap.counterparties[cp_key]["name"]
    target = snap.entities[entity]["display_name"] if entity else None
    label = snap.categories[category]["labels"]["en"] if category else None
    name = " → ".join(x for x in (cp_name, " / ".join(y for y in (target, label) if y)) if x)
    row, _ = store.save_rule(
        conn, key=store.unique_key(conn, name), name=name, state="draft", source="correction",
        body=body, priority=learned_priority(1, matched), names=snap.names,
        origin_document_id=doc["id"],
    )  # fmt: skip
    entry = store.journal_rule(
        conn, "rule.create", None, row, actor=actor, via=via, at=at, group_id=group_id
    )
    return row, entry


def _rule(conn: Connection, rule_id: str) -> Mapping[str, Any]:
    row = store.rule_row(conn, rule_id)
    if row is None:
        raise ServiceError("not_found", f"Unknown rule {rule_id}.")
    return row


def _applied_group(conn: Connection, rule_id: str) -> str | None:
    """C1 §11.5: the latest `rule_apply` group of the rule whose live state isn't `undone`."""
    g = T["op_groups"]
    groups = conn.execute(
        select(g.c.id)
        .where(g.c.rule_id == rule_id, g.c.kind == "rule_apply")
        .order_by(g.c.created_at.desc(), g.c.id.desc())
    ).scalars()
    for gid in groups:
        if group_state(conn, gid)[0] != "undone":
            return gid
    return None


def _move(doc: Mapping[str, Any], before: Mapping[str, Any], after: Mapping[str, Any]) -> RuleMove:
    frm, frm_name = split(before["path"])
    to, to_name = split(after["path"])
    return RuleMove(
        document_id=doc["id"],
        title=doc["title"] or doc["original_name"],
        from_=frm if before["location"] == "archive" else [],
        from_file_name=frm_name,
        to=to,
        to_file_name=to_name,
    )


def _candidates(ctx: Ctx, conn: Connection, snap: Snapshot, rule_id: str) -> list[Candidate]:
    return rule_candidates(conn, snap, registry.rule_specs(conn), rule_id, ctx.textcache)


def _stays(c: Candidate) -> bool:
    return c.doc["location"] == "archive" and is_suffix_of(c.doc["current_path"], c.placement.path)


def preview_rule(ctx: Ctx, rule_id: str, *, lang: str = "en") -> RulePreview:
    """C4 §3.8; once applied, the application itself (C1 §11.5 "Applied")."""
    with ctx.engine.connect() as conn:
        row = _rule(conn, rule_id)
        snap = registry.load(conn)
        cands = _candidates(ctx, conn, snap, rule_id)
        applied = _applied_group(conn, rule_id)
        if applied is None:
            moves = [
                _move(c.doc, {"location": c.doc["location"], "path": c.doc["current_path"]},
                      {"location": "archive", "path": c.placement.path})
                for c in cands if not _stays(c)
            ]  # fmt: skip
            stays = [c.doc["id"] for c in cands if _stays(c)]
        else:
            f, d = T["file_ops"], T["documents"]
            entries = (
                conn.execute(
                    select(f, d.c.title, d.c.original_name)
                    .join(d, d.c.id == f.c.document_id)
                    .where(f.c.group_id == applied, f.c.fs_state == "done")
                    .order_by(f.c.id)
                )
                .mappings()
                .all()
            )
            moves = [_move({**e, "id": e["document_id"]}, e["before"], e["after"]) for e in entries]
            in_group = {e["document_id"] for e in entries}
            stays = [c.doc["id"] for c in cands if c.doc["id"] not in in_group]
        return RulePreview(
            rule=rule_dto(snap, row, lang),
            moves=moves,
            moves_total=len(moves),
            stays=stays,
            stays_total=len(stays),
            applied=applied is not None,
            group_id=applied,
        )


@dataclass
class Applied:
    """C4 §3.9 result, plus the refreshed preview for the `rulePreview` card."""

    rule_id: str
    group_id: str | None
    moved: int
    unchanged: int
    failed: list[dict[str, str]] = field(default_factory=list)
    preview: RulePreview | None = None


def _classify(
    conn: Connection, snap: Snapshot, c: Candidate, rule_id: str, ctx: Ctx
) -> tuple[str, int, str]:
    """A `rule` classification for a candidate (C5 §9 with the rule as winner)."""
    ef = T["extraction_fields"]
    fields = {}
    if c.doc["extraction_id"]:
        fields = dict(
            conn.execute(
                select(ef.c.key, ef.c.verified).where(ef.c.extraction_id == c.doc["extraction_id"])
            ).all()
        )
    s = snap.settings
    dest = c.destination
    sc = score(
        rule_won=True, entity_set=True, model_confidence=None, category_unknown=False,
        fields=fields, tokens=tokens_used(dest.path_template, dest.file_template),
        fallbacks=c.placement.rendered.fallbacks, low=s["confidence_low"],
        high=s["confidence_high"],
    )  # fmt: skip
    p = c.placement
    cls_id = new_id("cls")
    conn.execute(
        insert(T["classifications"]).values(
            id=cls_id, document_id=c.doc["id"], extraction_id=c.doc["extraction_id"],
            method="rule", rule_id=rule_id,
            entity_id=snap.entities[p.entity]["id"],
            sub_unit_id=snap.sub_units[(p.entity, p.unit)]["id"] if p.unit else None,
            category_id=p.category, subcategory_key=p.subcategory,
            counterparty_id=c.doc["counterparty_id"], confidence=sc.confidence, band=sc.band,
            reasons=[], proposed_path=p.rendered.folder, proposed_file_name=p.rendered.file_name,
        )
    )  # fmt: skip
    return cls_id, sc.confidence, sc.band


def apply_rule(ctx: Ctx, rule_id: str, *, actor: str, via: str, lang: str = "en") -> Applied:
    """C4 §3.9: activate, then move every "moves" candidate in one `rule_apply` group."""
    now = ctx.clock()
    with ctx.engine.begin() as conn:
        row = _rule(conn, rule_id)
        body = RuleBody.model_validate({"conditions": row["conditions"], "action": row["action"]})
        if unresolved(body, store.registry(conn)):
            raise ServiceError("conflict", "The rule is invalid.", hint="rule_invalid")
        snap = registry.load(conn)
        cands = _candidates(ctx, conn, snap, rule_id)
        moves = [c for c in cands if not _stays(c)]
        group = None
        if moves:
            group = new_id("grp")
            conn.execute(
                insert(T["op_groups"]).values(
                    id=group, kind="rule_apply", actor=actor, via=via, rule_id=rule_id
                )
            )
        changed = store.set_state(
            conn, rule_id, "active", actor=actor, via=via, at=now, group_id=group
        )
        planned = [(c, *_classify(conn, snap, c, rule_id, ctx)) for c in moves]
    if changed:
        with ctx.engine.connect() as conn:
            store.write_export(conn, ctx.config_dir, now=now)
    out = Applied(rule_id, group, 0, len(cands) - len(moves))
    for c, cls_id, confidence, band in planned:
        doc = c.doc
        action = "file"
        if doc["location"] == "archive":
            same = doc["current_path"].rpartition("/")[0] == c.placement.rendered.folder
            action = "rename" if same else "move"
        change = Change(
            document_id=doc["id"], action=action, location="archive", path=c.placement.path,  # type: ignore[arg-type]
            actor=actor, via=via, expected=(doc["location"], doc["current_path"]),
            status="filed", reasons=(), classification_id=cls_id, rule_id=rule_id,
            group_id=group, entry_rule_id=rule_id, confidence=confidence, band=band,
            resolution="rule_applied",
        )  # fmt: skip
        try:
            r = ctx.ops.move(change)
        except FileOpError as err:
            out.failed.append({"document_id": doc["id"], "code": error_code(err)})
            continue
        if r.outcome == "moved":
            out.moved += 1
            with ctx.engine.begin() as conn:
                store.record_firing(conn, rule_id, now)
        else:
            out.unchanged += 1
    out.preview = preview_rule(ctx, rule_id, lang=lang)
    return out

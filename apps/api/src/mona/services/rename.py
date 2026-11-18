"""`rename_documents` (C4 §3.18, A62 item 1): a draft rule that carries a file name, checked
to be rename-only before anything is written."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError
from sqlalchemy import Connection, select

from mona.rules import store
from mona.rules.engine import RuleSpec, destination, learned_priority
from mona.rules.grammar import RuleAction, RuleBody, unresolved
from mona.services import registry
from mona.services.context import Ctx
from mona.services.errors import ServiceError
from mona.services.placement import Candidate, render_values, rule_candidates, subject
from mona.services.registry import Snapshot, T
from mona.services.rules import Visible, stays_in_place
from mona.templates import TOKENS, TemplateError, parse
from mona.templates.infer import InferError, check_literals, infer
from mona.templates.render import file_date

UNSAVED = "rul_unsaved"
VALID_TOKENS = sorted(
    [f"{{{t}}}" for t in TOKENS - {"date"}]
    + [f"{{date:{u}}}" for u in ("YYYY", "YY", "MMMM", "MM", "DD")]
)


@dataclass
class Rename:
    """C4 §3.18 result; `renames` lists every rename, this document first."""

    rule_id: str
    pattern: str
    renames_total: int
    renames: list[dict[str, str]] = field(default_factory=list)
    collisions: list[dict[str, Any]] = field(default_factory=list)
    not_covered: int = 0
    date_fallbacks: int = 0


def _invalid(message: str, field_: str, **kw: Any) -> ServiceError:
    return ServiceError("invalid_argument", message, field=field_, **kw)


def _filing_rule(conn: Connection, doc: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """The rule whose classification filed the document (method `rule`), if it still exists."""
    if doc["classification_id"] is None:
        return None
    c = T["classifications"]
    cls = conn.execute(select(c).where(c.c.id == doc["classification_id"])).mappings().first()
    if cls is None or cls["method"] != "rule" or cls["rule_id"] is None:
        return None
    return store.rule_row(conn, cls["rule_id"])


def _base(
    snap: Snapshot, doc: Mapping[str, Any], s: Any, filing: Mapping[str, Any] | None
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Conditions and action without `filename`: the filing rule's, else the Subject values'."""
    if filing is not None:
        action = {k: v for k, v in filing["action"].items() if k != "filename"}
        return list(filing["conditions"]), action
    entity = snap.entity_keys.get(doc["entity_id"])
    unit = snap.sub_unit_keys.get(doc["sub_unit_id"], (None, None))[1]
    if s.entity is None or s.model_category is None or (s.entity, s.model_category) != (
        entity, doc["category_id"]
    ):  # fmt: skip
        raise ServiceError(
            "conflict", "This document isn't filed where Mona read it, so a rule on what Mona "
            "reads would move it; only names can change here.", hint="would_refile",
        )  # fmt: skip
    conditions = [
        {"field": f, "op": "equals", "value": v}
        for f, v in (
            ("counterparty", snap.counterparty_keys[doc["counterparty_id"]]),
            ("entity", s.entity),
            ("category", s.model_category),
        )
    ]
    action = {"entity": entity, "unit": unit, "category": doc["category_id"],
              "subcategory": doc["subcategory_key"]}  # fmt: skip
    return conditions, {k: v for k, v in action.items() if v is not None}


def _pattern(example: str | None, pattern: str | None, values: Any) -> str:
    if example is not None:
        try:
            return infer(example, values).pattern
        except InferError as e:
            raise _invalid(e.message, "example", hint=e.hint) from None
    assert pattern is not None
    try:
        parts = parse(pattern, "file")
    except TemplateError as e:
        raise ServiceError(
            "invalid_argument", f"The pattern is not valid: {e.message} at offset {e.offset}.",
            field="pattern", valid=VALID_TOKENS, hint=f"offset {e.offset}",
        ) from None  # fmt: skip
    try:
        check_literals(parts, file_date(values))
    except InferError as e:
        raise _invalid(e.message, "pattern", hint=e.hint) from None
    return pattern


def _existing(conn: Connection, body: RuleBody) -> Mapping[str, Any] | None:
    t = T["rules"]
    conditions = [c.model_dump() for c in body.conditions]
    action = body.action.model_dump()
    for r in conn.execute(
        select(t).where(t.c.source == "correction").order_by(t.c.created_at, t.c.id)
    ).mappings():
        if r["conditions"] == conditions and r["action"] == action:
            return r
    return None


def _refiles(snap: Snapshot, c: Candidate) -> bool:
    doc, p = c.doc, c.placement
    now = (
        snap.entity_keys.get(doc["entity_id"]),
        snap.sub_unit_keys.get(doc["sub_unit_id"], (None, None))[1],
        doc["category_id"],
        doc["subcategory_key"],
        doc["current_path"].rpartition("/")[0],
    )
    return now != (p.entity, p.unit, p.category, p.subcategory, p.rendered.folder)


def _check(snap: Snapshot, cands: list[Candidate]) -> None:
    """A62 1.3: rename-only, and nothing waiting in Review."""
    waiting = [c for c in cands if c.doc["status"] != "filed" or c.doc["location"] != "archive"]
    if waiting:
        raise ServiceError(
            "conflict", f"{len(waiting)} of these document(s) are waiting in Review; they need "
            "filing before they can be renamed.", hint="in_review",
        )  # fmt: skip
    moving = [c for c in cands if _refiles(snap, c)]
    if moving:
        raise ServiceError(
            "conflict", f"This would also move {len(moving)} document(s) to another folder, "
            "entity or category; only names can change here.", hint="would_refile",
        )  # fmt: skip


def _not_covered(
    conn: Connection, doc: Mapping[str, Any], cands: list[Candidate], visible: Visible
) -> int:
    d = T["documents"]
    rows = conn.execute(
        select(d).where(
            d.c.counterparty_id == doc["counterparty_id"],
            d.c.deleted_at.is_(None),
            d.c.location == "archive",
        )
    ).mappings()
    ids = {c.doc["id"] for c in cands}
    return sum(1 for r in rows if r["id"] not in ids and (visible is None or visible(r)))


def rename_documents(
    ctx: Ctx,
    document_id: str,
    *,
    actor: str,
    via: str,
    example: str | None = None,
    pattern: str | None = None,
    visible: Visible = None,
) -> Rename:
    """C4 §3.18: derive the pattern, build the draft rule, refuse unless every candidate only
    changes name; the same input returns the same draft."""
    if (example is None) == (pattern is None):
        raise _invalid("Give exactly one of example or pattern.", "example")
    now = ctx.clock()
    d, b = T["documents"], T["batches"]
    created = False
    with ctx.engine.begin() as conn:
        doc = (
            conn.execute(select(d).where(d.c.id == document_id, d.c.deleted_at.is_(None)))
            .mappings()
            .first()
        )
        if doc is None:
            raise ServiceError("not_found", f"Unknown document {document_id}.")
        if conn.execute(select(b.c.visitor).where(b.c.id == doc["batch_id"])).scalar():
            raise ServiceError("not_allowed", "Visitors documents are never renamed by a rule.")
        if doc["status"] != "filed":
            raise ServiceError("conflict", "The document is waiting in Review; it needs filing "
                               "before it can be renamed.", hint="in_review")  # fmt: skip
        if doc["counterparty_id"] is None:
            raise _invalid("The document has no counterparty; correct that first.", "document_id")
        snap = registry.load(conn)
        specs = registry.rule_specs(conn)
        s = subject(conn, snap, doc, ctx.textcache)
        filing = _filing_rule(conn, doc)
        conditions, action = _base(snap, doc, s, filing)
        try:
            base = RuleAction.model_validate(action)
        except ValidationError as e:
            raise ServiceError(
                "conflict", "The filing rule is invalid.", hint="rule_invalid"
            ) from e
        dest = destination(base, s, snap.world)
        cp = dest.counterparty or snap.counterparty_keys[doc["counterparty_id"]]
        values = render_values(
            snap, doc, entity=dest.entity, unit=dest.unit, category=dest.category,
            subcategory=dest.subcategory, counterparty=cp,
        )  # fmt: skip
        if values.entity is None or values.category_labels is None:
            raise ServiceError("conflict", "The document has no entity or category to keep.",
                               hint="would_refile")  # fmt: skip
        filename = _pattern(example, pattern, values)
        body = RuleBody.model_validate(
            {"conditions": conditions, "action": {**action, "filename": filename}}
        )
        problems = unresolved(body, store.registry(conn))
        if problems:
            raise ServiceError("conflict", problems[0], hint="rule_invalid")
        row = _existing(conn, body)
        if row is None:
            matched = [
                r.priority for r in specs if r.state == "active" and r.matches(s, snap.world)
            ]
            floor = [filing["priority"]] if filing is not None else []
            spec = RuleSpec(
                UNSAVED, learned_priority(len(body.conditions), [*matched, *floor]), now,
                tuple(body.conditions), body.action, "draft",
            )  # fmt: skip
            specs.append(spec)
        cands = rule_candidates(conn, snap, specs, row["id"] if row else UNSAVED, ctx.textcache)
        _check(snap, cands)
        if row is None:
            cat = snap.categories[dest.category]["labels"]["en"] if dest.category else ""
            name = f"Rename {snap.counterparties[cp]['name']} {cat}".strip()
            row, _ = store.save_rule(
                conn, key=store.unique_key(conn, name), name=name, state="draft",
                source="correction", body=body, priority=spec.priority, names=snap.names,
                origin_document_id=document_id,
            )  # fmt: skip
            store.journal_rule(conn, "rule.create", None, row, actor=actor, via=via, at=now)
            created = True
        shown = [c for c in cands if visible is None or visible(c.doc)]
        moving = [c for c in shown if not stays_in_place(c)]
        targets = ctx.ops.predict_names([(c.doc, c.placement.path) for c in moving])
        not_covered = _not_covered(conn, doc, cands, visible)
    if created:
        with ctx.engine.connect() as conn:
            store.write_export(conn, ctx.config_dir, now=now)
    out = _result(row, body, moving, targets, not_covered)
    out.renames.sort(key=lambda r: r["document_id"] != document_id)
    return out


def _result(
    row: Mapping[str, Any],
    body: RuleBody,
    moving: list[Candidate],
    targets: list[str],
    not_covered: int,
) -> Rename:
    out = Rename(row["id"], body.action.filename or "", len(moving), not_covered=not_covered)
    groups: dict[str, list[str]] = {}
    for c, to in zip(moving, targets, strict=True):
        out.renames.append(
            {
                "document_id": c.doc["id"],
                "title": c.doc["title"] or c.doc["original_name"],
                "from_name": c.doc["current_path"].rpartition("/")[2],
                "to_name": to.rpartition("/")[2],
            }
        )
        groups.setdefault(c.placement.path, []).append(to)
        out.date_fallbacks += "date" in c.placement.rendered.fallbacks
    out.collisions = [
        {"to_name": base.rpartition("/")[2], "count": len(names)}
        for base, names in groups.items()
        if any(n != base for n in names)
    ]
    return out

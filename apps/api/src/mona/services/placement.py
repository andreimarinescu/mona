"""Where a document belongs: the rules Subject, a destination's rendering, rule candidates."""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, select

from mona.rules.engine import Destination, RuleSpec, Subject, destination, evaluate
from mona.services.registry import Snapshot, T
from mona.templates import NotRenderable, Rendered, RenderValues, render


def page_text(textcache: Path, sha256: str) -> str:
    """All pages joined with a space (C5 §4.2 `text`); empty when not extracted yet."""
    p = textcache / sha256[:2] / f"{sha256}.pages.json"
    try:
        return " ".join(json.loads(p.read_text(encoding="utf-8"))["pages"])
    except (OSError, ValueError, KeyError):
        return ""


def model_values(conn: Connection, doc: Mapping[str, Any]) -> dict[str, str | None]:
    """The model's category, subcategory and entity from the current extraction (C5 §5.2)."""
    out: dict[str, str | None] = {"category": None, "subcategory": None, "entity": None}
    if doc["extraction_id"] is None:
        return out
    x = T["extractions"]
    raw = conn.execute(select(x.c.raw_output).where(x.c.id == doc["extraction_id"])).scalar()
    if not raw:
        return out
    out["category"] = raw.get("category")
    sub = raw.get("subcategory")
    if isinstance(sub, str) and "." in sub and sub.split(".", 1)[0] == out["category"]:
        out["subcategory"] = sub.split(".", 1)[1]
    ent = raw.get("entity")
    out["entity"] = ent.get("value") if isinstance(ent, dict) else None
    return out


def subject(conn: Connection, snap: Snapshot, doc: Mapping[str, Any], textcache: Path) -> Subject:
    m = model_values(conn, doc)
    amount = doc["amount"] if doc["currency"] in ("EUR", "RON") else None
    return Subject(
        text=page_text(textcache, doc["sha256"]),
        counterparty=snap.counterparty_keys.get(doc["counterparty_id"]),
        doc_type=doc["doc_type"],
        category=m["category"],
        subcategory=m["subcategory"],
        entity=m["entity"],
        addressee=doc["addressee"],
        addressee_person=snap.people_keys.get(doc["addressee_person_id"]),
        amount=amount,
    )


@dataclass(frozen=True)
class Placement:
    """A renderable destination: registry keys plus the rendered path."""

    entity: str
    unit: str | None
    category: str
    subcategory: str | None
    counterparty: str | None
    rendered: Rendered

    @property
    def path(self) -> str:
        return self.rendered.path


def render_values(
    snap: Snapshot,
    doc: Mapping[str, Any],
    *,
    entity: str | None,
    unit: str | None,
    category: str | None,
    subcategory: str | None,
    counterparty: str | None,
) -> RenderValues:
    cat = snap.categories.get(category) if category else None
    sub = snap.subcategories.get((category, subcategory)) if category and subcategory else None
    cp = snap.counterparties.get(counterparty) if counterparty else None
    return RenderValues(
        entity=snap.entity_info(entity),
        arrived_at=doc["arrived_at"],
        language=snap.language,
        sub_unit_label=snap.sub_units[(entity, unit)]["label"] if entity and unit else None,
        category_labels=cat["labels"] if cat else None,
        subcategory_labels=sub["labels"] if sub else None,
        counterparty=cp["name"] if cp else None,
        issuer=doc["issuer"],
        reference=doc["reference"],
        doc_date=doc["doc_date"],
        period_end=doc["period_end"],
        mime_type=doc["mime_type"],
    )


def place(
    snap: Snapshot,
    doc: Mapping[str, Any],
    *,
    entity: str | None,
    unit: str | None,
    category: str | None,
    subcategory: str | None,
    counterparty: str | None,
    path_template: str | None = None,
    file_template: str | None = None,
) -> Placement | None:
    """Render with the template lookup (C1 §2.7); None when no path can be rendered."""
    if entity is None or category is None:
        return None
    tpl = snap.world.template(category, entity)
    path_t = path_template or (tpl[0] if tpl else None)
    file_t = file_template or (tpl[1] if tpl else None)
    if path_t is None or file_t is None:
        return None
    v = render_values(
        snap, doc, entity=entity, unit=unit, category=category, subcategory=subcategory,
        counterparty=counterparty,
    )  # fmt: skip
    try:
        rendered = render(path_t, file_t, v)
    except NotRenderable:
        return None
    return Placement(entity, unit, category, subcategory, counterparty, rendered)


def place_destination(
    snap: Snapshot, doc: Mapping[str, Any], dest: Destination
) -> Placement | None:
    """A rule destination; None when it can't file (unresolved unit, `review`, no path)."""
    if dest.unit_unresolved or dest.review:
        return None
    counterparty = dest.counterparty or snap.counterparty_keys.get(doc["counterparty_id"])
    return place(
        snap, doc, entity=dest.entity, unit=dest.unit, category=dest.category,
        subcategory=dest.subcategory, counterparty=counterparty,
        path_template=dest.path_template, file_template=dest.file_template,
    )  # fmt: skip


@dataclass(frozen=True)
class Candidate:
    doc: Mapping[str, Any]
    destination: Destination
    placement: Placement


def rule_candidates(
    conn: Connection,
    snap: Snapshot,
    specs: Sequence[RuleSpec],
    rule_id: str,
    textcache: Path,
) -> list[Candidate]:
    """C4 §3.8, C5 §4.6.9, A2: live filed/review documents outside visitor batches for which
    the rule, treated as active, is in T with no conflict, and whose destination renders."""
    d, b = T["documents"], T["batches"]
    rows = conn.execute(
        select(d)
        .join(b, b.c.id == d.c.batch_id)
        .where(d.c.deleted_at.is_(None), d.c.status.in_(("filed", "review")), ~b.c.visitor)
        .order_by(d.c.arrived_at, d.c.id)
    ).mappings()
    spec = next(s for s in specs if s.id == rule_id)
    out = []
    for doc in rows:
        s = subject(conn, snap, doc, textcache)
        if not spec.matches(s, snap.world):
            continue
        outcome = evaluate(specs, s, snap.world, as_active=rule_id)
        if rule_id not in outcome.top or outcome.conflict:
            continue
        dest = destination(spec.action, s, snap.world)
        placement = place_destination(snap, doc, dest)
        if placement is not None:
            out.append(Candidate(doc, dest, placement))
    return out

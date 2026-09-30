"""C1 §11 DTOs built from rows."""

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import Connection, select

from mona.dto import DocumentSummary, JournalEntry, JournalGroup, Money, PathState, Rule
from mona.fileops import badge_until, group_state, undo_state
from mona.rules.grammar import RuleAction, UnitFrom
from mona.rules.text import Names, render_condition_text
from mona.services.registry import Snapshot, T
from mona.templates import Token, parse

PATH_ACTIONS = {"file", "move", "rename", "unfile", "delete", "undo", "redo"}


def split(path: str) -> tuple[list[str], str]:
    folders, _, name = path.rpartition("/")
    return (folders.split("/") if folders else []), name


def path_state(state: Mapping[str, Any]) -> PathState:
    folders, name = split(state["path"])
    return PathState(
        location=state["location"], path=folders, file_name=name, status=state["status"]
    )


def journal_entry(
    conn: Connection, e: Mapping[str, Any], doc: Mapping[str, Any] | None = None
) -> JournalEntry:
    state = undo_state(conn, e, doc) if e["document_id"] else "not_undoable"
    path = e["action"] in PATH_ACTIONS
    return JournalEntry(
        id=e["id"],
        at=e["at"],
        actor=e["actor"],
        via=e["via"],
        action=e["action"],
        document_ids=[e["document_id"]] if e["document_id"] else [],
        subject_id=e["subject_id"],
        before=path_state(e["before"]) if path and e["before"] else e["before"],
        after=path_state(e["after"]) if path and e["after"] else e["after"],
        batch_id=e["batch_id"],
        group_id=e["group_id"],
        rule_id=e["rule_id"],
        confidence=e["confidence"],
        band=e["band"],
        undoable=state == "undoable",
        undo_state=state,
        undone_by=e["undone_by"],
        undo_of=e["undo_of"],
    )


def journal_group(conn: Connection, group_id: str) -> JournalGroup:
    g = T["op_groups"]
    row = conn.execute(select(g).where(g.c.id == group_id)).mappings().one()
    state, counts = group_state(conn, group_id)
    return JournalGroup(
        id=row["id"],
        kind=row["kind"],
        at=row["created_at"],
        actor=row["actor"],
        via=row["via"],
        batch_id=row["batch_id"],
        rule_id=row["rule_id"],
        counts=counts,
        undo_state=state,
        target_group_id=row["target_group_id"],
    )


def document_summary(
    conn: Connection, snap: Snapshot, doc: Mapping[str, Any], now: datetime
) -> DocumentSummary:
    folders, name = split(doc["current_path"])
    ent = snap.entities.get(snap.entity_keys.get(doc["entity_id"], ""))
    cp = snap.counterparties.get(snap.counterparty_keys.get(doc["counterparty_id"], ""))
    rule = None
    if doc["rule_id"]:
        r = T["rules"]
        name_ = conn.execute(select(r.c.name).where(r.c.id == doc["rule_id"])).scalar()
        rule = {"id": doc["rule_id"], "name": name_}
    until = badge_until(doc, snap.settings["badge_hours"], now)
    return DocumentSummary(
        id=doc["id"],
        title=doc["title"] or doc["original_name"],
        original_name=doc["original_name"],
        file_name=name,
        path=folders if doc["location"] == "archive" else [],
        location="archive" if doc["location"] == "archive" else "inbox",
        entity_id=doc["entity_id"],
        entity_name=ent["display_name"] if ent else None,
        sub_unit_id=doc["sub_unit_id"],
        category_id=doc["category_id"],
        subcategory_key=doc["subcategory_key"],
        counterparty_id=doc["counterparty_id"],
        counterparty=cp["name"] if cp else None,
        doc_type=doc["doc_type"],
        reference=doc["reference"],
        date=doc["doc_date"],
        period_start=doc["period_start"],
        period_end=doc["period_end"],
        fiscal_year=doc["fiscal_year"],
        amount=Money(value=doc["amount"], currency=doc["currency"]) if doc["currency"] else None,
        due_date=doc["due_date"],
        status=doc["status"],
        reasons=list(doc["reasons"]),
        confidence=doc["confidence"],
        band=doc["band"],
        pipeline_stage=doc["pipeline_stage"],
        arrived_at=doc["arrived_at"],
        source=doc["source"],
        filed_at=doc["filed_at"],
        filed_by=doc["filed_by"],
        badge_until=until,
        rule=rule,
        batch_id=doc["batch_id"],
        page_count=doc["page_count"],
        thumbnail_url=None,
        pdf_url=f"/api/documents/{doc['id']}/pdf",
    )


def destination(snap: Snapshot, action: RuleAction, conditions: list[Any]) -> list[str]:
    """C5 §4.7 `destination`: the effective path template with resolvable tokens filled."""
    entity, category = action.entity, action.category
    tpl = snap.world.template(category, entity) if category else None
    template = action.path or (tpl[0] if tpl else "{entity}/{category}")
    lang = snap.lang_for(entity)
    cp_key = action.counterparty
    if cp_key is None:
        eq = [c for c in conditions if c.field == "counterparty" and c.op == "equals"]
        if len(eq) == 1:
            cp_key = _counterparty_key(snap, eq[0].value)
    values: dict[str, str | None] = {
        "entity": snap.entities[entity]["folder_name"] if entity else None,
        "category": snap.categories[category]["labels"][lang] if category else None,
        "sub": (
            snap.subcategories[(category, action.subcategory)]["labels"][lang]
            if category and action.subcategory
            else None
        ),
        "counterparty": snap.counterparties[cp_key]["name"] if cp_key else None,
    }
    out: list[str] = []
    for segment in template.split("/"):
        parts = parse(segment, "path")
        if len(parts) == 1 and isinstance(parts[0], Token) and parts[0].name == "entity":
            out.append(values["entity"] or "{entity}")
            if isinstance(action.unit, UnitFrom):
                out.append("{person}")
            elif action.unit and entity:
                out.append(snap.sub_units[(entity, action.unit)]["label"])
            continue
        text = ""
        for p in parts:
            if isinstance(p, str):
                text += p
            else:
                raw = "{" + p.name + (f":{p.format}" if p.format else "") + "}"
                text += values.get(p.name) or raw
        out.append(text)
    return out


def _counterparty_key(snap: Snapshot, value: str) -> str | None:
    from mona.text import norm

    n = norm(value)
    for key, cp in snap.world.counterparties.items():
        if n in {norm(key), cp.name_norm, *cp.alias_norms}:
            return key
    return None


def rule(snap: Snapshot, row: Mapping[str, Any], lang: str = "en") -> Rule:
    from mona.rules.grammar import Condition

    conditions = [Condition.model_validate(c) for c in row["conditions"]]
    action = RuleAction.model_validate(row["action"])
    text = row["condition_text"].get(lang) or row["condition_text"]["en"]
    return Rule(
        id=row["id"],
        name=row["name"],
        condition=text,
        condition_text=text,
        conditions=conditions,
        action=action,
        destination=destination(snap, action, conditions),
        enabled=row["state"] == "active",
        state=row["state"],
        source=row["source"],
        version=row["version"],
        priority=row["priority"],
        fired_count=row["fired_count"],
        last_fired_at=row["last_fired_at"],
        corrections_since=row["corrections_since"],
    )


def condition_text(snap: Snapshot, conditions: list[Any]) -> dict[str, str]:
    names: Names = snap.names
    return render_condition_text(conditions, names)

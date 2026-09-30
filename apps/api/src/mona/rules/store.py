"""Rule rows: writes with versions (C1 §3), journal entries, C5 §4.8 statistics, §10 export."""

import os
import re
import shutil
import unicodedata
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import Connection, func, insert, select, update

from mona.db.models import Base
from mona.ids import new_id
from mona.rules.grammar import Registry, RuleBody
from mona.rules.text import Names, render_condition_text
from mona.seed.rules_export import dump_rules_yaml, export_rules

T = Base.metadata.tables
CORE = ("conditions", "action", "priority")
SNAPSHOT = ("key", "name", "state", "source", "priority", "conditions", "action", "version")


def names(conn: Connection) -> Names:
    acc = T["accounts"]
    return Names(
        people={r.key: r.display_name for r in conn.execute(select(T["people"]))},
        entities={r.key: r.display_name for r in conn.execute(select(T["entities"]))},
        accounts={
            r.key: f"{r.label} •• {r.iban_last4}"
            for r in conn.execute(select(acc.c.key, acc.c.label, acc.c.iban_last4))
        },
        categories={r.id: r.labels for r in conn.execute(select(T["categories"]))},
    )


def registry(conn: Connection) -> Registry:
    """The keys a rule may reference, from the DB (C5 §4.2.9)."""
    reg = Registry()
    ent = {r.id: r for r in conn.execute(select(T["entities"]))}
    reg.entities = {r.key for r in ent.values()}
    reg.visitors_entity = next(
        (r.key for r in ent.values() if r.purge_after_hours is not None), None
    )
    for r in conn.execute(select(T["sub_units"])):
        reg.sub_units.setdefault(ent[r.entity_id].key, set()).add(r.key)
    reg.people = set(conn.execute(select(T["people"].c.key)).scalars())
    reg.accounts = set(conn.execute(select(T["accounts"].c.key)).scalars())
    reg.counterparties = set(conn.execute(select(T["counterparties"].c.key)).scalars())
    reg.categories = set(conn.execute(select(T["categories"].c.id)).scalars())
    for r in conn.execute(select(T["subcategories"])):
        reg.subcategories.setdefault(r.category_id, set()).add(r.key)
    return reg


def snapshot(row: Mapping[str, Any]) -> dict[str, Any]:
    """The `before`/`after` of a `rule.*` journal entry."""
    return {k: row[k] for k in SNAPSHOT}


def rule_row(conn: Connection, rule_id: str) -> Mapping[str, Any] | None:
    t = T["rules"]
    return conn.execute(select(t).where(t.c.id == rule_id)).mappings().first()


def save_rule(
    conn: Connection,
    *,
    key: str,
    name: str,
    state: str,
    source: str,
    body: RuleBody,
    priority: int | None,
    names: Names,
    origin_document_id: str | None = None,
    origin_question_id: str | None = None,
) -> tuple[Mapping[str, Any], str]:
    """Upsert by key; a changed conditions/action/priority bumps the version (C1 §3).

    Returns the row and `inserted`, `updated` or `unchanged`. Writes no journal entry."""
    t, versions = T["rules"], T["rule_versions"]
    conditions = [c.model_dump() for c in body.conditions]
    core = {
        "conditions": conditions,
        "action": body.action.model_dump(),
        "priority": priority if priority is not None else 10 * len(conditions),
    }
    text = render_condition_text(body.conditions, names)
    row = conn.execute(select(t).where(t.c.key == key)).mappings().first()
    if row is None:
        rid = new_id("rul")
        conn.execute(
            insert(t).values(
                id=rid,
                key=key,
                name=name,
                state=state,
                source=source,
                condition_text=text,
                origin_document_id=origin_document_id,
                origin_question_id=origin_question_id,
                **core,
            )
        )
        conn.execute(insert(versions).values(rule_id=rid, version=1, condition_text=text, **core))
        return rule_row(conn, rid), "inserted"  # type: ignore[return-value]
    wanted = {"name": name, "state": state, "source": source, "condition_text": text, **core}
    changed: dict[str, Any] = {k: v for k, v in wanted.items() if row[k] != v}
    if not changed:
        return row, "unchanged"
    if any(k in changed for k in CORE):
        changed |= {"version": row["version"] + 1, "corrections_since": 0}
        conn.execute(
            insert(versions).values(
                rule_id=row["id"], version=changed["version"], condition_text=text, **core
            )
        )
    conn.execute(update(t).where(t.c.id == row["id"]).values(updated_at=func.now(), **changed))
    return rule_row(conn, row["id"]), "updated"  # type: ignore[return-value]


def journal_rule(
    conn: Connection,
    action: str,
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any],
    *,
    actor: str,
    via: str,
    at: datetime,
    group_id: str | None = None,
) -> int:
    """A `rule.create` / `rule.change` entry (not undoable in v1, C7 §2.1)."""
    f = T["file_ops"]
    return conn.execute(
        insert(f)
        .values(
            at=at,
            actor=actor,
            via=via,
            action=action,
            subject_id=after["id"],
            rule_id=after["id"],
            before=snapshot(before) if before is not None else None,
            after=snapshot(after),
            group_id=group_id,
            undoable=False,
        )
        .returning(f.c.id)
    ).scalar_one()


def set_state(
    conn: Connection,
    rule_id: str,
    state: str,
    *,
    actor: str,
    via: str,
    at: datetime,
    group_id: str | None = None,
) -> int | None:
    """Change `state` (no version bump); journals `rule.change` when it changed."""
    before = rule_row(conn, rule_id)
    if before is None or before["state"] == state:
        return None
    t = T["rules"]
    conn.execute(update(t).where(t.c.id == rule_id).values(state=state, updated_at=func.now()))
    after = rule_row(conn, rule_id)
    return journal_rule(
        conn, "rule.change", before, after, actor=actor, via=via, at=at, group_id=group_id
    )  # type: ignore[arg-type]


def record_firing(conn: Connection, rule_id: str, at: datetime, n: int = 1) -> None:
    """C5 §4.8: a rule won for a classification (or moved a document when applied)."""
    t = T["rules"]
    conn.execute(
        update(t).where(t.c.id == rule_id).values(fired_count=t.c.fired_count + n, last_fired_at=at)
    )


def record_correction(conn: Connection, rule_id: str) -> None:
    t = T["rules"]
    conn.execute(
        update(t).where(t.c.id == rule_id).values(corrections_since=t.c.corrections_since + 1)
    )


def slug_key(name: str) -> str:
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:36].strip("-")
    if not re.match(r"^[a-z][a-z0-9-]{1,}$", s):
        s = f"rule-{s}".strip("-")[:36]
    return s


def unique_key(conn: Connection, name: str) -> str:
    """C1 §3: generated from the name, `-2`, `-3` on a clash."""
    base = slug_key(name)
    t = T["rules"]
    taken = set(conn.execute(select(t.c.key).where(t.c.key.like(f"{base}%"))).scalars())
    if base not in taken:
        return base
    return next(f"{base}-{n}" for n in range(2, 10_000) if f"{base}-{n}" not in taken)


def write_export(conn: Connection, config_dir: Path, *, now: datetime | None = None) -> Path:
    """C5 §10: rewrite `rules.yaml` atomically; keep the previous one in `rules.history/`."""
    config_dir.mkdir(parents=True, exist_ok=True)
    target = config_dir / "rules.yaml"
    doc = export_rules(conn, now=now)
    if target.exists():
        previous = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
        history = config_dir / "rules.history"
        history.mkdir(exist_ok=True)
        shutil.copyfile(target, history / f"rules-{previous.get('revision', 0)}.yaml")
    tmp = config_dir / "rules.yaml.tmp"
    tmp.write_text(dump_rules_yaml(doc), encoding="utf-8")
    os.replace(tmp, target)
    return target

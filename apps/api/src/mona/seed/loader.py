"""`mona seed load`: C1 §9 seed loader (registry, settings, profile and rules)."""

import logging
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml
from argon2 import PasswordHasher
from pydantic import ValidationError
from sqlalchemy import Connection, Table, and_, func, insert, select, update
from sqlalchemy.exc import IntegrityError

from mona.db.models import Base
from mona.iban import iban_candidates, iban_hash, iban_last4, is_valid_iban
from mona.ids import new_id
from mona.rules.grammar import Registry, RuleBody, unresolved
from mona.rules.text import Names, render_condition_text
from mona.seed.files import (
    PracticeFile,
    Problem,
    RuleIn,
    RulesFile,
    SeedError,
)
from mona.settings import Settings
from mona.templates import TemplateError, parse
from mona.text import norm

log = logging.getLogger(__name__)

Tier = Literal["preseeded", "all"]
RULE_FILES: dict[str, list[str]] = {
    "preseeded": ["rules.yaml"],
    "all": ["rules.yaml", "rules.learned.yaml"],
}
KEY = re.compile(r"^[a-z][a-z0-9-]{1,39}$")
CATEGORY_ID = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
SUBCATEGORY_KEY = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
DS_ICONS = {"bank", "invoice", "tax", "insurance", "payroll", "training", "travel", "personal"}
LANGS = ("en", "fr", "ro")
MONTH_DAYS = {2: 28, 4: 30, 6: 30, 9: 30, 11: 30}

T: dict[str, Table] = Base.metadata.tables  # type: ignore[assignment]


@dataclass
class Summary:
    inserted: Counter[str] = field(default_factory=Counter)
    updated: Counter[str] = field(default_factory=Counter)

    def __str__(self) -> str:
        tables = sorted(set(self.inserted) | set(self.updated))
        parts = [f"{t} +{self.inserted[t]} ~{self.updated[t]}" for t in tables]
        return "seed loaded: " + (", ".join(parts) if parts else "no changes")


# --- reading ---


def _read_yaml(path: Path, where: str, problems: list[Problem]) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        problems.append(Problem(0, where, f"missing file {path.name}"))
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        line = f" at line {mark.line + 1}" if mark else ""
        problems.append(Problem(0, where, f"invalid YAML{line}"))
    return None


def _label(node: Any, index: int) -> Any:
    return node.get("key", node.get("id", index)) if isinstance(node, dict) else index


def _walk(node: Any, path: str):
    yield path, node
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _walk(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, f"{path}[{_label(v, i)}]")


def _iban_literals(raw: Any, where: str) -> list[Problem]:
    return [
        Problem(3, path, "a clear IBAN; move it to the overlay and use {ref: ...}")
        for path, value in _walk(raw, where)
        if isinstance(value, str) and iban_candidates(value)
    ]


UNRESOLVED = "<unresolved>"


def _resolve_refs(node: Any, overlay: dict[str, Any] | None, path: str, missing: dict[str, str]):
    """Replace `{ref: a.b}` with overlay values; unresolved ones are recorded in `missing`."""
    if isinstance(node, dict):
        if set(node) == {"ref"}:
            value: Any = overlay
            for part in str(node["ref"]).split("."):
                value = value.get(part) if isinstance(value, dict) else None
            if value is None:
                missing[path] = str(node["ref"])
                return UNRESOLVED
            return value
        return {k: _resolve_refs(v, overlay, f"{path}.{k}", missing) for k, v in node.items()}
    if isinstance(node, list):
        return [
            _resolve_refs(v, overlay, f"{path}[{_label(v, i)}]", missing)
            for i, v in enumerate(node)
        ]
    return node


def _keyed(raw: Any, where: str, loc: tuple) -> str:
    out, node = where, raw
    for part in loc:
        if isinstance(part, int) and isinstance(node, list) and part < len(node):
            node = node[part]
            out += f"[{_label(node, part)}]"
        else:
            node = node.get(part) if isinstance(node, dict) else None
            out += f".{part}"
    return out


def _parse(model: Any, raw: Any, where: str, problems: list[Problem]) -> Any:
    try:
        return model.model_validate(raw)
    except ValidationError as e:
        for err in e.errors(include_input=False, include_url=False):
            problems.append(Problem(0, _keyed(raw, where, tuple(err["loc"])), err["msg"]))
    return None


# --- file-level checks (invariants 1 format, 4, 5, 7) ---


def _duplicates(keys: list[str], where: str) -> list[Problem]:
    return [Problem(1, where, f"duplicate key {k!r}") for k, n in Counter(keys).items() if n > 1]


def _check_practice(p: PracticeFile) -> list[Problem]:
    out: list[Problem] = []
    for kind, keys in [
        ("people", [x.key for x in p.people]),
        ("entities", [x.key for x in p.entities]),
        ("accounts", [x.key for x in p.accounts]),
        ("counterparties", [x.key for x in p.counterparties]),
    ]:
        out += _duplicates(keys, kind)
        out += [
            Problem(1, f"{kind}[{k}]", "key must match ^[a-z][a-z0-9-]{1,39}$")
            for k in keys
            if not KEY.match(k)
        ]
    out += _duplicates([c.id for c in p.categories], "categories")
    out += _duplicates([e.folder_name for e in p.entities], "entities.folder_name")
    visitors = [e.key for e in p.entities if e.purge_after_hours is not None]
    if len(visitors) > 1:
        out.append(Problem(0, "entities", f"more than one Visitors entity: {visitors}"))
    for e in p.entities:
        out += _duplicates([s.key for s in e.sub_units], f"entities[{e.key}].sub_units")
        out += [
            Problem(1, f"entities[{e.key}].sub_units[{s.key}]", "bad key")
            for s in e.sub_units
            if not KEY.match(s.key)
        ]
        month, day = e.fy_end_month, e.fy_end_day
        if not (1 <= month <= 12 and 1 <= day <= MONTH_DAYS.get(month, 31)):
            out.append(Problem(0, f"entities[{e.key}].fy_end_day", "not a valid fiscal-year end"))
    sirens = [(f"entities[{e.key}]", e.siren) for e in p.entities]
    sirens += [(f"counterparties[{c.key}]", c.siren) for c in p.counterparties]
    for where, siren in sirens:
        if siren not in (None, UNRESOLVED) and not re.fullmatch(r"[0-9]{9}", siren):
            out.append(Problem(0, f"{where}.siren", "must be 9 digits"))
    for c in p.categories:
        where = f"categories[{c.id}]"
        if not CATEGORY_ID.match(c.id):
            out.append(Problem(1, where, "id must match ^[a-z][a-z0-9_]{1,39}$"))
        if c.icon not in DS_ICONS:
            out.append(Problem(4, f"{where}.icon", f"{c.icon!r} is not in the DS Category union"))
        out += _labels(c.labels, f"{where}.labels")
        out += _duplicates([s.key for s in c.subcategories], f"{where}.subcategories")
        for s in c.subcategories:
            if not SUBCATEGORY_KEY.match(s.key):
                out.append(Problem(1, f"{where}.subcategories[{s.key}]", "bad key"))
            out += _labels(s.labels, f"{where}.subcategories[{s.key}].labels")
    defaults = Counter(t.category for t in p.templates if t.entity is None)
    pairs = Counter((t.category, t.entity) for t in p.templates)
    for (cat, ent), n in pairs.items():
        if n > 1 and ent is not None:
            out.append(Problem(0, f"templates[{cat}/{ent}]", "duplicate entity template"))
    for c in p.categories:
        if defaults[c.id] != 1:
            out.append(
                Problem(
                    7,
                    f"categories[{c.id}]",
                    f"{defaults[c.id]} default templates; exactly one is required",
                )
            )
    for t in p.templates:
        where = f"templates[{t.category}/{t.entity or 'default'}]"
        for kind, value in (("path", t.path_template), ("file", t.file_template)):
            try:
                parse(value, kind)  # type: ignore[arg-type]
            except TemplateError as e:
                out.append(Problem(5, f"{where}.{kind}_template", str(e)))
    return out


def _labels(labels: dict[str, str], where: str) -> list[Problem]:
    missing = [lang for lang in LANGS if not str(labels.get(lang) or "").strip()]
    extra = sorted(set(labels) - set(LANGS))
    out = [Problem(4, where, f"missing {', '.join(missing)} label")] if missing else []
    if extra:
        out.append(Problem(4, where, f"unknown label languages {extra}"))
    return out


# --- registry snapshot and references (invariant 1) ---


def _snapshot(conn: Connection) -> Registry:
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


def _merge(reg: Registry, p: PracticeFile) -> Registry:
    reg.entities |= {e.key for e in p.entities}
    visitors = next((e.key for e in p.entities if e.purge_after_hours is not None), None)
    reg.visitors_entity = visitors or reg.visitors_entity
    for e in p.entities:
        reg.sub_units.setdefault(e.key, set()).update(s.key for s in e.sub_units)
    reg.people |= {x.key for x in p.people}
    reg.accounts |= {a.key for a in p.accounts}
    reg.counterparties |= {c.key for c in p.counterparties}
    reg.categories |= {c.id for c in p.categories}
    for c in p.categories:
        reg.subcategories.setdefault(c.id, set()).update(s.key for s in c.subcategories)
    return reg


def _practice_refs(p: PracticeFile, reg: Registry) -> list[Problem]:
    out: list[Problem] = []

    def need(ok: bool, where: str, what: str, value: str) -> None:
        if not ok:
            out.append(Problem(1, where, f"unknown {what} {value!r}"))

    for e in p.entities:
        for s in e.sub_units:
            if s.person:
                need(
                    s.person in reg.people,
                    f"entities[{e.key}].sub_units[{s.key}].person",
                    "person",
                    s.person,
                )
        for link in e.people:
            need(link.person in reg.people, f"entities[{e.key}].people", "person", link.person)
    for t in p.templates:
        where = f"templates[{t.category}/{t.entity or 'default'}]"
        need(t.category in reg.categories, f"{where}.category", "category", t.category)
        if t.entity is not None:
            need(t.entity in reg.entities, f"{where}.entity", "entity", t.entity)
    for a in p.accounts:
        where = f"accounts[{a.key}]"
        need(a.entity in reg.entities, f"{where}.entity", "entity", a.entity)
        if a.sub_unit:
            need(
                a.sub_unit in reg.sub_units.get(a.entity, set()),
                f"{where}.sub_unit",
                f"sub-unit of {a.entity!r}",
                a.sub_unit,
            )
        if a.bank_counterparty:
            need(
                a.bank_counterparty in reg.counterparties,
                f"{where}.bank_counterparty",
                "counterparty",
                a.bank_counterparty,
            )
    return out


# --- writing ---


def _upsert(
    conn: Connection,
    table: str,
    match: dict[str, Any],
    values: dict[str, Any],
    summary: Summary,
    *,
    prefix: str | None = None,
) -> Any:
    t = T[table]
    where = and_(*[t.c[k] == v for k, v in match.items()])
    row = conn.execute(select(t).where(where)).mappings().first()
    if row is None:
        new = {**match, **values}
        if prefix:
            new["id"] = new_id(prefix)
        conn.execute(insert(t).values(new))
        summary.inserted[table] += 1
        return new.get("id")
    changed = {k: v for k, v in values.items() if row[k] != v}
    if changed:
        if "updated_at" in t.c:
            changed["updated_at"] = func.now()
        conn.execute(update(t).where(where).values(changed))
        summary.updated[table] += 1
    return row.get("id")


def _ids(conn: Connection, table: str, column: str = "key") -> dict[str, str]:
    t = T[table]
    return {k: i for k, i in conn.execute(select(t.c[column], t.c.id))}


def _write_settings(conn: Connection, p: PracticeFile, settings: Settings, s: Summary) -> bytes:
    info = p.practice
    values: dict[str, Any] = {"practice_name": info.name, "filing_language": info.filing_language}
    for name in ("confidence_high", "confidence_low", "badge_hours", "debrief_queue_threshold"):
        if getattr(info, name) is not None:
            values[name] = getattr(info, name)
    row = conn.execute(select(T["settings"])).mappings().first()
    pepper = settings.mona_iban_pepper.get_secret_value() if settings.mona_iban_pepper else None
    if pepper and not re.fullmatch(r"[0-9a-fA-F]{64}", pepper):
        raise SeedError([Problem(0, "MONA_IBAN_PEPPER", "must be 64 hex characters")])
    if row is None:
        salt = bytes.fromhex(pepper) if pepper else os.urandom(32)
        _upsert(conn, "settings", {"singleton": True}, {**values, "iban_salt": salt}, s)
        return salt
    if pepper and bytes.fromhex(pepper) != bytes(row["iban_salt"]):
        log.warning("MONA_IBAN_PEPPER differs from settings.iban_salt; keeping the stored salt")
    _upsert(conn, "settings", {"singleton": True}, values, s)
    return bytes(row["iban_salt"])


def _write_profile(conn: Connection, p: PracticeFile, settings: Settings, s: Summary) -> None:
    values = {"name": p.practice.owner_name or p.practice.name, "locale": p.practice.locale}
    exists = conn.execute(select(T["profile"].c.singleton)).first()
    if exists is None:
        password = settings.mona_owner_password
        if password is None:
            raise SeedError([Problem(0, "profile", "MONA_OWNER_PASSWORD is not set")])
        values["password_hash"] = PasswordHasher().hash(password.get_secret_value())
    _upsert(conn, "profile", {"singleton": True}, values, s)


def _write_registry(conn: Connection, p: PracticeFile, salt: bytes, s: Summary) -> None:
    for x in p.people:
        _upsert(
            conn,
            "people",
            {"key": x.key},
            {"display_name": x.display_name, "short_name": x.short_name, "aliases": x.aliases},
            s,
            prefix="per",
        )
    people = _ids(conn, "people")
    for i, e in enumerate(p.entities):
        _upsert(
            conn,
            "entities",
            {"key": e.key},
            {
                "display_name": e.display_name,
                "folder_name": e.folder_name,
                "legal_form": e.legal_form,
                "siren": e.siren,
                "visibility": e.visibility,
                "fy_end_month": e.fy_end_month,
                "fy_end_day": e.fy_end_day,
                "filing_language": e.filing_language,
                "aliases": e.aliases,
                "addresses": e.addresses,
                "purge_after_hours": e.purge_after_hours,
                "sort_order": e.sort_order if e.sort_order is not None else i,
            },
            s,
            prefix="ent",
        )
    entities = _ids(conn, "entities")
    for e in p.entities:
        eid = entities[e.key]
        for sub in e.sub_units:
            _upsert(
                conn,
                "sub_units",
                {"entity_id": eid, "key": sub.key},
                {"label": sub.label, "person_id": people.get(sub.person or "")},
                s,
                prefix="sub",
            )
        for link in e.people:
            _upsert(
                conn,
                "entity_people",
                {"entity_id": eid, "person_id": people[link.person]},
                {"role": link.role},
                s,
            )
    _write_counterparties(conn, p, s)
    for i, c in enumerate(p.categories):
        _upsert(
            conn,
            "categories",
            {"id": c.id},
            {
                "labels": c.labels,
                "icon": c.icon,
                "model_definition": c.model_definition,
                "sort_order": c.sort_order if c.sort_order is not None else i,
            },
            s,
        )
        for j, sub in enumerate(c.subcategories):
            _upsert(
                conn,
                "subcategories",
                {"category_id": c.id, "key": sub.key},
                {
                    "labels": sub.labels,
                    "sort_order": j if sub.sort_order is None else sub.sort_order,
                },
                s,
            )
    for t in p.templates:
        _upsert(
            conn,
            "templates",
            {"category_id": t.category, "entity_id": entities.get(t.entity or "")},
            {"path_template": t.path_template, "file_template": t.file_template},
            s,
            prefix="tpl",
        )
    counterparties = _ids(conn, "counterparties")
    subs = {
        (r.entity_id, r.key): r.id
        for r in conn.execute(
            select(T["sub_units"].c.entity_id, T["sub_units"].c.key, T["sub_units"].c.id)
        )
    }
    for a in p.accounts:
        eid = entities[a.entity]
        _upsert(
            conn,
            "accounts",
            {"key": a.key},
            {
                "entity_id": eid,
                "sub_unit_id": subs.get((eid, a.sub_unit)) if a.sub_unit else None,
                "bank_counterparty_id": counterparties.get(a.bank_counterparty or ""),
                "label": a.label,
                "iban_hash": iban_hash(a.iban, salt),
                "iban_last4": iban_last4(a.iban),
                "currency": a.currency,
            },
            s,
            prefix="acc",
        )


def _write_counterparties(conn: Connection, p: PracticeFile, s: Summary) -> None:
    problems: list[Problem] = []
    for c in p.counterparties:
        values = {"name": c.name, "name_norm": norm(c.name), "kind": c.kind, "siren": c.siren}
        t = T["counterparties"]
        exists = conn.execute(select(t.c.id).where(t.c.key == c.key)).first()
        clash = conn.execute(
            select(t.c.key).where(t.c.name_norm == values["name_norm"], t.c.key != c.key)
        ).first()
        if clash:
            problems.append(
                Problem(
                    0,
                    f"counterparties[{c.key}].name",
                    f"same normalised name as counterparty {clash.key!r}",
                )
            )
            continue
        cid = _upsert(
            conn,
            "counterparties",
            {"key": c.key},
            values if exists else {**values, "origin": "seed"},
            s,
            prefix="cpt",
        )
        aliases = dict.fromkeys([values["name_norm"], *(norm(a) for a in c.aliases)])
        for alias in aliases:
            a = T["counterparty_aliases"]
            owner = conn.execute(
                select(t.c.key, t.c.id)
                .join(a, a.c.counterparty_id == t.c.id)
                .where(a.c.alias_norm == alias)
            ).first()
            if owner is None:
                conn.execute(insert(a).values(alias_norm=alias, counterparty_id=cid))
                s.inserted["counterparty_aliases"] += 1
            elif owner.id != cid:
                problems.append(
                    Problem(
                        0,
                        f"counterparties[{c.key}].aliases",
                        f"alias {alias!r} already belongs to {owner.key!r}",
                    )
                )
    if problems:
        raise SeedError(problems)


def _names(conn: Connection) -> Names:
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


def _write_rules(conn: Connection, rules: list[tuple[RuleIn, RuleBody]], s: Summary) -> None:
    names = _names(conn)
    t, versions = T["rules"], T["rule_versions"]
    for r, body in rules:
        conditions = [c.model_dump() for c in body.conditions]
        action = body.action.model_dump()
        priority = r.priority if r.priority is not None else 10 * len(conditions)
        text = render_condition_text(body.conditions, names)
        row = conn.execute(select(t).where(t.c.key == r.key)).mappings().first()
        core = {"conditions": conditions, "action": action, "priority": priority}
        if row is None:
            rid = new_id("rul")
            conn.execute(
                insert(t).values(
                    id=rid,
                    key=r.key,
                    name=r.name,
                    state=r.state,
                    source=r.source,
                    condition_text=text,
                    **core,
                )
            )
            conn.execute(
                insert(versions).values(rule_id=rid, version=1, condition_text=text, **core)
            )
            s.inserted["rules"] += 1
            continue
        changed: dict[str, Any] = {
            k: v
            for k, v in {
                "name": r.name,
                "state": r.state,
                "source": r.source,
                "condition_text": text,
                **core,
            }.items()
            if row[k] != v
        }
        if not changed:
            continue
        if any(k in changed for k in core):
            changed |= {"version": row["version"] + 1, "corrections_since": 0}
            conn.execute(
                insert(versions).values(
                    rule_id=row["id"], version=changed["version"], condition_text=text, **core
                )
            )
        conn.execute(update(t).where(t.c.id == row["id"]).values(updated_at=func.now(), **changed))
        s.updated["rules"] += 1


# --- entry point ---


def read_overlay(path: Path | None, problems: list[Problem]) -> dict[str, Any] | None:
    if path is None:
        return None
    data = _read_yaml(path, "overlay", problems)
    if data is not None and not isinstance(data, dict):
        problems.append(Problem(0, "overlay", "must be a mapping"))
        return None
    return data


def load_seed(
    conn: Connection,
    seed_dir: Path,
    *,
    settings: Settings,
    tier: Tier = "preseeded",
    overlay: Path | None = None,
) -> Summary:
    """Validate and upsert the seed in the caller's transaction; raises SeedError."""
    problems: list[Problem] = []
    overlay_data = read_overlay(overlay, problems)
    raw_practice = _read_yaml(seed_dir / "practice.yaml", "practice.yaml", problems)
    raw_rules = [(name, _read_yaml(seed_dir / name, name, problems)) for name in RULE_FILES[tier]]
    if problems:
        raise SeedError(problems)

    problems += _iban_literals(raw_practice, "practice.yaml")
    for name, raw in raw_rules:
        problems += _iban_literals(raw, name)
    for i, acc in enumerate((raw_practice or {}).get("accounts") or []):
        iban = acc.get("iban") if isinstance(acc, dict) else None
        if not (isinstance(iban, dict) and set(iban) == {"ref"}):
            key = acc.get("key", i) if isinstance(acc, dict) else i
            problems.append(
                Problem(
                    3,
                    f"practice.yaml.accounts[{key}].iban",
                    "must be an overlay reference {ref: ...}",
                )
            )
    missing: dict[str, str] = {}
    resolved = _resolve_refs(raw_practice, overlay_data, "practice.yaml", missing)
    reason = "no overlay loaded" if overlay_data is None else "not in the overlay"
    problems += [
        Problem(1, path, f"unresolved overlay reference {ref!r} ({reason})")
        for path, ref in missing.items()
    ]
    parsed: list[Problem] = []
    practice = _parse(PracticeFile, resolved, "practice.yaml", parsed)
    problems += [p for p in parsed if p.where not in missing]
    files = [(name, _parse(RulesFile, raw, name, problems)) for name, raw in raw_rules]
    if practice is None or any(f is None for _, f in files):
        raise SeedError(problems)

    problems += _check_practice(practice)
    for a in practice.accounts:
        if a.iban != UNRESOLVED and not is_valid_iban(a.iban):
            problems.append(
                Problem(3, f"accounts[{a.key}].iban", "the overlay value is not a valid IBAN")
            )

    rules: list[tuple[RuleIn, RuleBody]] = []
    all_keys = [r.key for _, f in files for r in f.rules]
    problems += _duplicates(all_keys, "rules")
    for name, f in files:
        for r in f.rules:
            where = f"{name}.rules[{r.key}]"
            if not KEY.match(r.key):
                problems.append(Problem(1, where, "key must match ^[a-z][a-z0-9-]{1,39}$"))
            try:
                body = RuleBody.model_validate({"conditions": r.conditions, "action": r.action})
            except ValidationError as e:
                problems += [
                    Problem(
                        6,
                        where + (f".{'.'.join(map(str, err['loc']))}" if err["loc"] else ""),
                        err["msg"],
                    )
                    for err in e.errors(include_input=False, include_url=False)
                ]
                continue
            rules.append((r, body))

    registry = _merge(_snapshot(conn), practice)
    problems += _practice_refs(practice, registry)
    for r, body in rules:
        for msg in unresolved(body, registry):
            where, _, what = msg.partition(": ")
            problems.append(Problem(1 if "unknown" in what else 6, f"rules[{r.key}].{where}", what))
    if problems:
        raise SeedError(problems)

    summary = Summary()
    try:
        with conn.begin_nested():
            salt = _write_settings(conn, practice, settings, summary)
            _write_profile(conn, practice, settings, summary)
            _write_registry(conn, practice, salt, summary)
            _write_rules(conn, rules, summary)
    except IntegrityError as e:
        constraint = getattr(getattr(e.orig, "diag", None), "constraint_name", None) or "unknown"
        raise SeedError([Problem(0, "database", f"rejected by constraint {constraint}")]) from None
    log.info("%s", summary)
    return summary

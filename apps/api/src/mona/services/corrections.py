"""`correct_document` (C4 §3.5), counterparty resolution and alias learning (C5 §6.2)."""

import re
import unicodedata
from collections.abc import Collection
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import Connection, delete, insert, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from mona.dto import DocumentSummary, Rule, RulePreview
from mona.fileops import Change, FileOpError, is_suffix_of
from mona.ids import new_id
from mona.rules import store
from mona.rules.grammar import RuleBody
from mona.services import registry
from mona.services.context import Ctx
from mona.services.dto import document_summary
from mona.services.errors import ServiceError
from mona.services.placement import place
from mona.services.registry import Snapshot, T
from mona.services.search_index import rebuild_fts
from mona.templates import document_fiscal_year
from mona.text import norm

FIELDS = ("doc_date", "period_end", "due_date", "amount", "currency")
CLASS = ("entity_id", "sub_unit_id", "category_id", "subcategory_key", "counterparty_id")
CLEARABLE = frozenset({"sub_unit", "subcategory", "due_date", "amount"})
MERGE_SIMILARITY = 0.6
ENTITY_SIMILARITY = 0.5


# --- resolvers (C4 §3 common filters) ---


def _invalid(field_: str, message: str, valid: list[Any]) -> ServiceError:
    return ServiceError(
        "invalid_argument", message, field=field_, valid=valid[:30] or None,
        hint="Use one of the valid values.",
    )  # fmt: skip


def resolve_entity(conn: Connection, snap: Snapshot, value: str) -> str:
    """Key, display name, folder name or alias by `norm()`, else one trigram match ≥ 0.5."""
    n = norm(value)
    for key, e in snap.entities.items():
        if n in {norm(x) for x in (key, e["display_name"], e["folder_name"], *e["aliases"])}:
            return key
    rows = (
        conn.execute(
            text(
                "SELECT key FROM entities WHERE similarity(lower(unaccent(display_name)), :v) >= :t"
            ),
            {"v": n, "t": ENTITY_SIMILARITY},
        )
        .scalars()
        .all()
    )
    if len(rows) == 1:
        return rows[0]
    valid = [
        {"key": k, "name": e["display_name"]}
        for k, e in snap.entities.items()
        if k != snap.visitors
    ]
    raise _invalid("entity", f"Unknown entity '{value}'.", valid)


def resolve_category(snap: Snapshot, value: str) -> str:
    n = norm(value)
    for cid, c in snap.categories.items():
        if n in {norm(cid), *(norm(v) for v in c["labels"].values())}:
            return cid
    valid = [{"id": cid, "label": c["labels"]["en"]} for cid, c in snap.categories.items()]
    raise _invalid("category", f"Unknown category '{value}'.", valid)


def resolve_subcategory(snap: Snapshot, category: str, value: str) -> str:
    n = norm(value)
    subs = {k: s for (c, k), s in snap.subcategories.items() if c == category}
    for key, s in subs.items():
        if n in {norm(key), *(norm(v) for v in s["labels"].values())}:
            return key
    valid = [{"key": k, "label": s["labels"]["en"]} for k, s in subs.items()]
    raise _invalid("subcategory", f"Unknown subcategory '{value}' of {category}.", valid)


def resolve_sub_unit(snap: Snapshot, entity: str, value: str) -> str:
    n = norm(value)
    units = {k: s for (e, k), s in snap.sub_units.items() if e == entity}
    for key, s in units.items():
        if n in {norm(key), norm(s["label"])}:
            return key
    valid = [{"key": k, "label": s["label"]} for k, s in units.items()]
    raise _invalid("sub_unit", f"Unknown sub-unit '{value}' of {entity}.", valid)


def _counterparty_key(conn: Connection, value: str) -> str:
    s = unicodedata.normalize("NFKD", value)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    base = re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:36].strip("-") or "counterparty"
    if not base[0].isalpha():
        base = f"cp-{base}"[:36]
    taken = set(
        conn.execute(
            select(T["counterparties"].c.key).where(T["counterparties"].c.key.like(f"{base}%"))
        ).scalars()
    )
    if base not in taken and len(base) >= 2:
        return base
    return next(f"{base}-{n}" for n in range(2, 100_000) if f"{base}-{n}" not in taken)


def resolve_counterparty(conn: Connection, value: str) -> str:
    """C5 §6.2.1: exact alias, else trigram ≥ 0.6, else a new `extracted` counterparty."""
    n = norm(value)
    if not n:
        raise ServiceError("invalid_argument", "Empty counterparty.", field="counterparty")
    a, c = T["counterparty_aliases"], T["counterparties"]
    hit = conn.execute(select(a.c.counterparty_id).where(a.c.alias_norm == n)).scalar()
    if hit:
        return hit
    hit = conn.execute(
        text(
            "SELECT id FROM counterparties WHERE similarity(name_norm, :n) >= :t"
            " ORDER BY similarity(name_norm, :n) DESC, id LIMIT 1"
        ),
        {"n": n, "t": MERGE_SIMILARITY},
    ).scalar()
    if hit:
        return hit
    conn.execute(
        pg_insert(c)
        .values(
            id=new_id("cpt"), key=_counterparty_key(conn, value), name=" ".join(value.split()),
            name_norm=n, origin="extracted",
        )
        .on_conflict_do_nothing(index_elements=["name_norm"])
    )  # fmt: skip
    cid = conn.execute(select(c.c.id).where(c.c.name_norm == n)).scalar_one()
    conn.execute(pg_insert(a).values(alias_norm=n, counterparty_id=cid).on_conflict_do_nothing())
    return cid


def _rename_key(value: Any, old: str, new: str) -> Any:
    if isinstance(value, list):
        return [new if v == old else v for v in value]
    return new if value == old else value


def merge_counterparty(
    conn: Connection, x: str, c: str, *, actor: str, via: str, at: datetime, group_id: str | None
) -> None:
    """C5 §6.2.5: fold the `extracted` counterparty `x` into `c`."""
    cp, d, cls, a = (
        T["counterparties"],
        T["documents"],
        T["classifications"],
        T["counterparty_aliases"],
    )
    x_key = conn.execute(select(cp.c.key).where(cp.c.id == x)).scalar_one()
    c_key = conn.execute(select(cp.c.key).where(cp.c.id == c)).scalar_one()
    conn.execute(update(d).where(d.c.counterparty_id == x).values(counterparty_id=c))
    conn.execute(update(cls).where(cls.c.counterparty_id == x).values(counterparty_id=c))
    conn.execute(update(a).where(a.c.counterparty_id == x).values(counterparty_id=c))
    names = store.names(conn)
    for r in conn.execute(select(T["rules"])).mappings().all():
        conds = [
            {**k, "value": _rename_key(k["value"], x_key, c_key)}
            if k["field"] == "counterparty" and k["op"] in ("equals", "in")
            else k
            for k in r["conditions"]
        ]
        action = dict(r["action"])
        if action.get("counterparty") == x_key:
            action["counterparty"] = c_key
        if conds == r["conditions"] and action == r["action"]:
            continue
        body = RuleBody.model_validate({"conditions": conds, "action": action})
        after, _ = store.save_rule(
            conn, key=r["key"], name=r["name"], state=r["state"], source=r["source"], body=body,
            priority=r["priority"], names=names,
        )  # fmt: skip
        store.journal_rule(
            conn, "rule.change", r, after, actor=actor, via=via, at=at, group_id=group_id
        )
    acc = T["accounts"]
    conn.execute(update(acc).where(acc.c.bank_counterparty_id == x).values(bank_counterparty_id=c))
    conn.execute(delete(cp).where(cp.c.id == x))


def learn_alias(
    conn: Connection,
    extracted: str | None,
    c: str,
    *,
    actor: str,
    via: str,
    at: datetime,
    group_id: str | None,
) -> str:
    """C5 §6.2.5; returns `inserted`, `known`, `merged`, `skipped` or `none`."""
    a_norm = norm(extracted or "")
    if not a_norm:
        return "none"
    a, cp = T["counterparty_aliases"], T["counterparties"]
    inserted = conn.execute(
        pg_insert(a)
        .values(alias_norm=a_norm, counterparty_id=c)
        .on_conflict_do_nothing()
        .returning(a.c.alias_norm)
    ).scalar()
    owner = conn.execute(
        select(a.c.counterparty_id).where(a.c.alias_norm == a_norm).with_for_update()
    ).scalar_one()
    if inserted:
        return "inserted"
    if owner == c:
        return "known"
    origin = conn.execute(select(cp.c.origin).where(cp.c.id == owner)).scalar_one()
    if origin != "extracted":
        return "skipped"
    merge_counterparty(conn, owner, c, actor=actor, via=via, at=at, group_id=group_id)
    return "merged"


# --- correct_document ---


@dataclass
class Correction:
    """C4 §3.5 result, with the C1 DTOs L2 renders."""

    document_id: str
    outcome: Literal["moved", "unchanged"]
    document: DocumentSummary
    journal_ids: list[int] = field(default_factory=list)
    group_id: str | None = None
    rule: Rule | None = None
    preview: RulePreview | None = None


def _jsonable(v: Any) -> Any:
    if isinstance(v, date | datetime):
        return v.isoformat()
    if isinstance(v, Decimal):
        return f"{v:.2f}"
    return v


def _extracted_counterparty(conn: Connection, doc: Any) -> str | None:
    if doc["extraction_id"] is None:
        return None
    ef = T["extraction_fields"]
    return conn.execute(
        select(ef.c.value).where(
            ef.c.extraction_id == doc["extraction_id"], ef.c.key == "counterparty"
        )
    ).scalar()


def correct_document(
    ctx: Ctx,
    document_id: str,
    *,
    actor: str,
    via: str,
    entity: str | None = None,
    sub_unit: str | None = None,
    category: str | None = None,
    subcategory: str | None = None,
    counterparty: str | None = None,
    doc_date: date | None = None,
    period_end: date | None = None,
    due_date: date | None = None,
    amount: Decimal | float | None = None,
    currency: str | None = None,
    scope: Literal["one", "all"] = "one",
    lang: str = "en",
    clear: Collection[str] = (),
) -> Correction:
    """Apply a stated correction and re-file (C4 §3.5); `scope='all'` drafts a rule; `clear`
    empties the named `CLEARABLE` values (C2 §6.2 nulls)."""
    from mona.services import rules as rules_service

    clear = frozenset(clear)
    assert clear <= CLEARABLE, clear
    given = (entity, sub_unit, category, subcategory, counterparty, doc_date, period_end,
             due_date, amount)  # fmt: skip
    if all(v is None for v in given) and not clear:
        raise ServiceError("invalid_argument", "Give at least one correction.", field="document_id")
    if (amount is None) != (currency is None) or currency not in (None, "EUR", "RON"):
        raise ServiceError("invalid_argument", "An amount needs a currency, EUR or RON.",
                           field="currency")  # fmt: skip
    d, b = T["documents"], T["batches"]
    now = ctx.clock()
    journal: list[int] = []
    rule_row: Any = None
    with ctx.engine.begin() as conn:
        doc = (
            conn.execute(select(d).where(d.c.id == document_id, d.c.deleted_at.is_(None)))
            .mappings()
            .first()
        )
        if doc is None:
            raise ServiceError("not_found", f"Unknown document {document_id}.")
        if doc["status"] == "processing":
            raise ServiceError("conflict", "The document is still being read.", hint="processing")
        snap = registry.load(conn)
        visitor = conn.execute(select(b.c.visitor).where(b.c.id == doc["batch_id"])).scalar()
        cur_entity = snap.entity_keys.get(doc["entity_id"])
        cur_unit = snap.sub_unit_keys.get(doc["sub_unit_id"], (None, None))[1]
        ent = cur_entity
        if entity is not None:
            ent = resolve_entity(conn, snap, entity)
            if ent == snap.visitors or (visitor and ent != cur_entity):
                raise ServiceError("not_allowed", "The Visitors entity can't be changed here.",
                                   field="entity")  # fmt: skip
        unit = cur_unit if ent == cur_entity and "sub_unit" not in clear else None
        if sub_unit is not None:
            if ent is None:
                raise ServiceError("invalid_argument", "A sub-unit needs an entity.",
                                   field="sub_unit")  # fmt: skip
            unit = resolve_sub_unit(snap, ent, sub_unit)
        cat = resolve_category(snap, category) if category is not None else doc["category_id"]
        sub = doc["subcategory_key"] if cat == doc["category_id"] else None
        if "subcategory" in clear:
            sub = None
        if subcategory is not None:
            if cat is None:
                raise ServiceError("invalid_argument", "A subcategory needs a category.",
                                   field="subcategory")  # fmt: skip
            sub = resolve_subcategory(snap, cat, subcategory)
        cp_id = doc["counterparty_id"]
        if counterparty is not None:
            cp_id = resolve_counterparty(conn, counterparty)
            snap = registry.load(conn)
        fields = {k: doc[k] for k in FIELDS}
        for k, v in (("doc_date", doc_date), ("period_end", period_end), ("due_date", due_date)):
            if v is not None:
                fields[k] = v
        if amount is not None:
            fields["amount"] = Decimal(str(amount)).quantize(Decimal("0.01"))
            fields["currency"] = currency
        if "amount" in clear:
            fields["amount"] = fields["currency"] = None
        if "due_date" in clear:
            fields["due_date"] = None
        changed_fields = {k: v for k, v in fields.items() if v != doc[k]}
        new_class = {
            "entity_id": snap.entities[ent]["id"] if ent else None,
            "sub_unit_id": snap.sub_units[(ent, unit)]["id"] if ent and unit else None,
            "category_id": cat,
            "subcategory_key": sub,
            "counterparty_id": cp_id,
        }
        changed_class = {k for k in CLASS if new_class[k] != doc[k]}
        preview_doc = {**doc, **fields}
        placement = place(
            snap, preview_doc, entity=ent, unit=unit, category=cat, subcategory=sub,
            counterparty=snap.counterparty_keys.get(cp_id),
        )  # fmt: skip
        if placement is None:
            raise ServiceError("invalid_argument",
                               "The document needs an entity and a category to be filed.",
                               field="entity" if ent is None else "category")  # fmt: skip
        in_place = doc["location"] == "archive" and is_suffix_of(
            doc["current_path"], placement.path
        )
        nothing = not changed_fields and not changed_class and doc["status"] == "filed"
        if nothing and in_place:
            if scope == "all":
                rule_row, rule_entry = rules_service.draft_from_correction(
                    conn, snap, doc, entity=ent, unit=unit, category=cat, subcategory=sub,
                    counterparty_id=cp_id, actor=actor, via=via, at=now, group_id=None,
                    textcache=ctx.textcache,
                )  # fmt: skip
                journal += [rule_entry] if rule_entry else []
            summary = document_summary(conn, snap, doc, now)
    if nothing and in_place:
        result = Correction(document_id, "unchanged", summary, journal)
        return _with_preview(ctx, result, rule_row, now, lang)
    with ctx.engine.begin() as conn:
        group = new_id("grp")
        conn.execute(
            insert(T["op_groups"]).values(id=group, kind="correction", actor=actor, via=via)
        )
        if counterparty is not None:
            learn_alias(conn, _extracted_counterparty(conn, doc), cp_id, actor=actor, via=via,
                        at=now, group_id=group)  # fmt: skip
        if changed_fields:
            journal.append(
                _doc_update(conn, doc, changed_fields, actor, via, now, group, snap, ent)
            )
        cls_id = new_id("cls")
        conn.execute(
            insert(T["classifications"]).values(
                id=cls_id, document_id=document_id, extraction_id=doc["extraction_id"],
                method="user", confidence=100, band="high", reasons=[],
                proposed_path=placement.rendered.folder,
                proposed_file_name=placement.rendered.file_name, **new_class,
            )
        )  # fmt: skip
        if doc["rule_id"] and (changed_class - {"counterparty_id"} or not in_place):
            store.record_correction(conn, doc["rule_id"])
        if scope == "all":
            rule_row, rule_entry = rules_service.draft_from_correction(
                conn, snap, doc, entity=ent, unit=unit, category=cat, subcategory=sub,
                counterparty_id=cp_id, actor=actor, via=via, at=now, group_id=group,
                textcache=ctx.textcache,
            )  # fmt: skip
            journal += [rule_entry] if rule_entry else []
    _, entry_id = _refile(ctx, document_id, doc, placement.path, cls_id, actor, via, group)
    if entry_id:
        journal.append(entry_id)
    with ctx.engine.connect() as conn:
        snap = registry.load(conn)
        doc = conn.execute(select(d).where(d.c.id == document_id)).mappings().one()
        summary = document_summary(conn, snap, doc, now)
    outcome: Literal["moved", "unchanged"] = "moved" if entry_id else "unchanged"
    result = Correction(document_id, outcome, summary, sorted(journal), group)
    return _with_preview(ctx, result, rule_row, now, lang)


def _with_preview(ctx: Ctx, result: Correction, rule_row: Any, now: datetime, lang: str):
    from mona.services import rules as rules_service

    if rule_row is not None:
        with ctx.engine.connect() as conn:
            store.write_export(conn, ctx.config_dir, now=now)
        result.preview = rules_service.preview_rule(ctx, rule_row["id"], lang=lang)
        result.rule = result.preview.rule
    return result


def _doc_update(conn, doc, changed, actor, via, now, group, snap, ent) -> int:
    d = T["documents"]
    values = dict(changed)
    merged = {**doc, **changed}
    values["fiscal_year"] = document_fiscal_year(
        snap.entity_info(ent), merged["period_end"], merged["doc_date"], doc["arrived_at"]
    )
    conn.execute(update(d).where(d.c.id == doc["id"]).values(updated_at=now, **values))
    f = T["file_ops"]
    return conn.execute(
        insert(f)
        .values(
            at=now, actor=actor, via=via, action="doc.update", document_id=doc["id"],
            before={k: _jsonable(doc[k]) for k in changed},
            after={k: _jsonable(v) for k, v in changed.items()},
            group_id=group, undoable=False,
        )
        .returning(f.c.id)
    ).scalar_one()  # fmt: skip


def _refile(
    ctx: Ctx, document_id: str, doc: Any, path: str, cls_id: str, actor: str, via: str, group: str
) -> tuple[Literal["moved", "unchanged"], int | None]:
    """Move to the rendered path; when the path is unchanged, apply the classification alone."""
    action = "file"
    if doc["location"] == "archive":
        same_folder = doc["current_path"].rpartition("/")[0] == path.rpartition("/")[0]
        action = "rename" if same_folder else "move"
    change = Change(
        document_id=document_id, action=action, location="archive", path=path, actor=actor,  # type: ignore[arg-type]
        via=via, expected=(doc["location"], doc["current_path"]), status="filed", reasons=(),
        classification_id=cls_id, rule_id=None, group_id=group, resolution="corrected",
    )  # fmt: skip
    try:
        r = ctx.ops.move(change)
    except FileOpError as err:
        if isinstance(err, ServiceError):
            raise
        raise ServiceError(
            "conflict" if err.code != "forbidden_path" else "forbidden_path",
            "The document could not be re-filed.", hint=err.hint or err.code,
        ) from None  # fmt: skip
    if r.outcome == "moved":
        return "moved", r.entry_id
    _apply_classification(ctx, document_id, cls_id)
    return "unchanged", None


def _apply_classification(ctx: Ctx, document_id: str, cls_id: str) -> None:
    """The path stays; the classification pointer and its fields change (no file op)."""
    d = T["documents"]
    with ctx.ops.locked(document_id) as conn, conn.begin():
        doc = conn.execute(select(d).where(d.c.id == document_id)).mappings().one()
        fields = ctx.ops._classified(conn, cls_id, doc)
        conn.execute(
            update(d)
            .where(d.c.id == document_id)
            .values(classification_id=cls_id, rule_id=None, updated_at=ctx.clock(), **fields)
        )
        rebuild_fts(conn, document_id, ctx.textcache)

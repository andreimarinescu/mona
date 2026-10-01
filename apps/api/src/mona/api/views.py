"""Sync C1 §11 / C2 DTO builders for the REST routes (run through `mona.api.deps.run`)."""

from collections.abc import Mapping
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import Connection, func, select

from mona import clock
from mona.dto import models as dto
from mona.i18n import t
from mona.rules.grammar import RuleAction, RuleBody, unresolved
from mona.rules.store import registry as rule_registry
from mona.services.dto import document_summary, journal_entry, rule
from mona.services.registry import Snapshot, T
from mona.settings import get_settings

FIELD_ORDER = (
    "entity", "counterparty", "issuer", "reference", "doc_type", "doc_date", "period_start",
    "period_end", "amount", "due_date", "addressee",
)  # fmt: skip
SENTENCE_ORDER = ("unreadable", "conflict", "entity", "asked", "low")


def thumbnail_url(doc: Mapping[str, Any]) -> str | None:
    sha = doc["sha256"]
    cache = get_settings().mona_data_dir / "textcache" / sha[:2] / f"{sha}.p1.png"
    return f"/api/documents/{doc['id']}/thumbnail" if cache.is_file() else None


def summary(conn: Connection, snap: Snapshot, doc: Mapping[str, Any]) -> dto.DocumentSummary:
    out = document_summary(conn, snap, doc, clock.now())
    out.thumbnail_url = thumbnail_url(doc)
    return out


def doc_row(conn: Connection, document_id: str, *, deleted: bool = False) -> Any:
    d = T["documents"]
    q = select(d).where(d.c.id == document_id)
    if not deleted:
        q = q.where(d.c.deleted_at.is_(None))
    return conn.execute(q).mappings().first()


def summaries(conn: Connection, snap: Snapshot, ids: list[str]) -> list[dto.DocumentSummary]:
    """In the order of `ids`; deleted or missing ids are skipped."""
    if not ids:
        return []
    d = T["documents"]
    rows = {
        r["id"]: r
        for r in conn.execute(select(d).where(d.c.id.in_(ids), d.c.deleted_at.is_(None))).mappings()
    }
    return [summary(conn, snap, rows[i]) for i in ids if i in rows]


def _title(doc: Mapping[str, Any]) -> str:
    return doc["title"] or doc["original_name"]


def fields(conn: Connection, doc: Mapping[str, Any]) -> list[dto.ExtractedField]:
    if doc["extraction_id"] is None:
        return []
    ef = T["extraction_fields"]
    rows = {
        r["key"]: r
        for r in conn.execute(
            select(ef).where(ef.c.extraction_id == doc["extraction_id"])
        ).mappings()
    }
    out = []
    for key in FIELD_ORDER:
        r = rows.get(key)
        if r is None:
            continue
        money = None
        if key == "amount" and r["currency"] in ("EUR", "RON"):
            try:
                money = dto.Money(value=Decimal(r["value"]), currency=r["currency"])
            except (InvalidOperation, ValueError):
                money = None
        out.append(
            dto.ExtractedField(
                key=key,
                value=r["value"],
                money=money,
                evidence=evidence(doc, r),
                confidence=r["confidence"],
            )
        )
    return out


def evidence(doc: Mapping[str, Any], r: Mapping[str, Any]) -> dto.Evidence:
    return dto.Evidence(
        document_id=doc["id"],
        document_title=_title(doc),
        field=r["key"],
        page=r["page"],
        quote=r["quote"],
        verified=r["verified"],
        find_query=r["find_query"],
    )


def sentence(
    snap: Snapshot,
    doc: Mapping[str, Any],
    *,
    entity_id: str | None,
    category_id: str | None,
    reasons: list[str],
    asked: bool,
    lang: str,
    first: bool = False,
) -> str:
    """C8 §5.4: the first of unreadable, conflict, entity, asked, low that applies, else default;
    `entity` reads as `first` when it came only from the first-seen signal (A17)."""
    applies = set(reasons)
    if entity_id is None:
        applies.add("entity")
    if asked and set(reasons) <= {"low"}:
        applies.discard("low")
        applies.add("asked")
    key = next((k for k in SENTENCE_ORDER if k in applies), "default")
    cp_key = snap.counterparty_keys.get(doc["counterparty_id"])
    counterparty = snap.counterparties[cp_key]["name"] if cp_key else None
    if key == "entity" and first and counterparty:
        key = "first"
    ent_key = snap.entity_keys.get(entity_id)
    cat = snap.categories.get(category_id) if category_id else None
    values = {
        "counterparty": counterparty or "",
        "docType": f" ({doc['doc_type']})" if doc["doc_type"] else "",
        "entity": snap.entities[ent_key]["display_name"] if ent_key else "",
        "category": cat["labels"].get(lang, cat["labels"]["en"]) if cat else "",
    }
    return t(f"review.sentence.{key}", lang, context=None if counterparty else "anon", **values)


def suggestion(
    conn: Connection, snap: Snapshot, doc: Mapping[str, Any], lang: str
) -> dto.Suggestion | None:
    if doc["status"] not in ("review", "unreadable"):
        return None
    c = T["classifications"]
    cls = None
    if doc["classification_id"]:
        cls = conn.execute(select(c).where(c.c.id == doc["classification_id"])).mappings().first()
    src: Mapping[str, Any] = cls or doc
    asked = False
    if cls and cls["rule_id"]:
        r = T["rules"]
        action = conn.execute(select(r.c.action).where(r.c.id == cls["rule_id"])).scalar()
        asked = bool(action and action.get("review"))
    reasons = list(doc["reasons"])
    folders = (cls["proposed_path"] or "").split("/") if cls and cls["proposed_path"] else []
    # A17: with an entity, no winning rule and a rendered path, `entity` has no other trigger.
    first = bool(
        cls
        and "entity" in reasons
        and cls["entity_id"] is not None
        and cls["rule_id"] is None
        and (cls["category_id"] is None or cls["proposed_path"] is not None)
    )
    ev = [f.evidence for f in fields(conn, doc)]
    return dto.Suggestion(
        entity_id=src["entity_id"],
        sub_unit_id=src["sub_unit_id"],
        category_id=src["category_id"],
        subcategory_key=src["subcategory_key"],
        file_name=cls["proposed_file_name"] if cls else None,
        path=folders,
        confidence=(cls["confidence"] if cls else doc["confidence"]) or 0,
        band=(cls["band"] if cls else doc["band"]) or "low",
        reasons=reasons,
        sentence=sentence(
            snap,
            doc,
            entity_id=src["entity_id"],
            category_id=src["category_id"],
            reasons=reasons,
            asked=asked,
            lang=lang,
            first=first,
        ),  # fmt: skip
        evidence=ev,
        rule_id=cls["rule_id"] if cls else None,
        conflicting_rule_ids=list(cls["conflicting_rule_ids"]) if cls else [],
    )


def deadlines(conn: Connection, where: Any, today: date | None = None) -> list[dto.Deadline]:
    """Deadline DTOs for the rows matching `where`, soonest first."""
    dl, e, a, r = T["deadlines"], T["entities"], T["accounts"], T["reminders"]
    today = today or clock.paris_today()
    rows = conn.execute(
        select(dl, e.c.display_name.label("entity_name"), a.c.label.label("account_label"),
               a.c.iban_last4)
        .join(e, e.c.id == dl.c.entity_id)
        .outerjoin(a, a.c.id == dl.c.paid_by_account_id)
        .where(where)
        .order_by(dl.c.due_date, dl.c.id)
    ).mappings().all()  # fmt: skip
    ids = [x["id"] for x in rows]
    nxt: dict[str, Any] = {}
    if ids:
        for rem in conn.execute(
            select(r.c.id, r.c.deadline_id, r.c.remind_on)
            .where(r.c.deadline_id.in_(ids), r.c.status == "scheduled")
            .order_by(r.c.remind_on.desc())
        ).mappings():
            nxt[rem["deadline_id"]] = rem
    return [
        dto.Deadline(
            id=x["id"],
            document_id=x["document_id"],
            label=x["label"],
            entity_id=x["entity_id"],
            entity_name=x["entity_name"],
            due_date=x["due_date"],
            amount=dto.Money(value=x["amount"], currency=x["currency"]) if x["currency"] else None,
            paid_by=f"{x['account_label']} •• {x['iban_last4']}" if x["account_label"] else None,
            status=x["status"],
            days_left=(x["due_date"] - today).days,
            reminder=(
                {"id": nxt[x["id"]]["id"], "remind_on": nxt[x["id"]]["remind_on"]}
                if x["id"] in nxt
                else None
            ),
        )
        for x in rows
    ]


def journal_of(conn: Connection, doc: Mapping[str, Any]) -> list[dto.JournalEntry]:
    f = T["file_ops"]
    rows = conn.execute(
        select(f)
        .where(f.c.document_id == doc["id"], f.c.fs_state == "done")
        .order_by(f.c.id.desc())
    ).mappings()
    return [journal_entry(conn, e, doc) for e in rows]


def detail(conn: Connection, snap: Snapshot, doc: Mapping[str, Any], lang: str) -> dict[str, Any]:
    """DocumentDetail (C1 §11.3, C2 §4.2) as a dict for the response model."""
    base = summary(conn, snap, doc).model_dump(by_alias=False)
    dl = T["deadlines"]
    return dto.DocumentDetail(
        **base,
        fields=fields(conn, doc),
        suggestion=suggestion(conn, snap, doc, lang),
        journal=journal_of(conn, doc),
        deadlines=deadlines(conn, dl.c.document_id == doc["id"]),
    ).model_dump(mode="json")


def rule_item(snap: Snapshot, row: Mapping[str, Any], lang: str, reg: Any) -> dict[str, Any]:
    """C2 §7 `RuleListItem`: the rule plus whether its references still resolve."""
    body = RuleBody.model_validate({"conditions": row["conditions"], "action": row["action"]})
    problems = unresolved(body, reg)
    try:
        r = rule(snap, row, lang)
    except (KeyError, ValueError):
        r = _rule_without_destination(row, lang)
    return {"rule": r.model_dump(mode="json"), "valid": not problems, "problems": problems}


def _rule_without_destination(row: Mapping[str, Any], lang: str) -> dto.Rule:
    text = row["condition_text"].get(lang) or row["condition_text"]["en"]
    return dto.Rule(
        id=row["id"], name=row["name"], condition=text, condition_text=text,
        conditions=row["conditions"], action=RuleAction.model_validate(row["action"]),
        destination=[], enabled=row["state"] == "active", state=row["state"],
        source=row["source"], version=row["version"], priority=row["priority"],
        fired_count=row["fired_count"], last_fired_at=row["last_fired_at"],
        corrections_since=row["corrections_since"],
    )  # fmt: skip


def registry_for_rules(conn: Connection) -> Any:
    return rule_registry(conn)


def batch_summary(conn: Connection, batch_id: str) -> dict[str, Any] | None:
    """C2 §5.2 `BatchSummary`; counts are computed, never stored (C1 §4.1)."""
    b, it, d, g = T["batches"], T["intake_items"], T["documents"], T["op_groups"]
    row = conn.execute(select(b).where(b.c.id == batch_id)).mappings().first()
    if row is None:
        return None
    outcomes = dict(
        conn.execute(
            select(it.c.outcome, func.count())
            .where(it.c.batch_id == batch_id)
            .group_by(it.c.outcome)
        ).all()
    )
    statuses = dict(
        conn.execute(
            select(d.c.status, func.count())
            .where(d.c.batch_id == batch_id, d.c.deleted_at.is_(None))
            .group_by(d.c.status)
        ).all()
    )
    failed = conn.execute(
        select(func.count()).where(d.c.batch_id == batch_id, d.c.pipeline_stage == "failed")
    ).scalar_one()
    group = conn.execute(
        select(g.c.id).where(g.c.batch_id == batch_id, g.c.kind == "intake_batch")
    ).scalar()
    debrief = None
    if row["debrief_interview_id"]:
        iv, q = T["interviews"], T["interview_questions"]
        status = conn.execute(
            select(iv.c.status).where(iv.c.id == row["debrief_interview_id"])
        ).scalar()
        open_q = conn.execute(
            select(func.count()).where(
                q.c.interview_id == row["debrief_interview_id"], q.c.status == "open"
            )
        ).scalar_one()
        if status is not None:
            debrief = {
                "interview_id": row["debrief_interview_id"],
                "status": status,
                "open_questions": open_q,
            }
    return {
        "id": row["id"],
        "source": row["source"],
        "status": row["status"],
        "title": row["title"],
        "visitor": row["visitor"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "counts": {
            "items": sum(outcomes.values()),
            "accepted": outcomes.get("accepted", 0),
            "duplicate": outcomes.get("duplicate", 0),
            "rejected": outcomes.get("rejected", 0),
            "processing": statuses.get("processing", 0),
            "filed": statuses.get("filed", 0),
            "review": statuses.get("review", 0),
            "unreadable": statuses.get("unreadable", 0),
            "failed": failed,
        },
        "group_id": group,
        "debrief": debrief,
    }


def count(conn: Connection, stmt: Any) -> int:
    return conn.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()

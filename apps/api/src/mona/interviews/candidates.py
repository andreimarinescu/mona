"""C6 §2: scopes, candidates, clusters (§4.2) and coverage (§3.3)."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Connection, func, or_, select

from mona.db.models import Base
from mona.interviews.config import MAX_CANDIDATES, MAX_SEED_COUNTERPARTIES
from mona.text import norm

T = Base.metadata.tables
PRIMARY_REASONS = ("conflict", "entity", "low")
SEED_KINDS = ("insurer", "bank", "accountant")


@dataclass
class Doc:
    id: str
    sha256: str
    arrived_at: datetime
    batch_id: str
    status: str
    reasons: list[str]
    title: str
    counterparty_id: str | None
    counterparty: str | None
    extracted_counterparty: str | None
    doc_type: str | None
    doc_date: Any
    amount: Decimal | None
    currency: str | None
    addressee: str | None
    extraction_id: str | None
    entity: str | None = None
    category: str | None = None
    subcategory: str | None = None
    confidence: int | None = None
    asked_only: bool = False

    @property
    def primary_reason(self) -> str | None:
        return next((r for r in PRIMARY_REASONS if r in self.reasons), None)

    @property
    def cluster_key(self) -> tuple[str, str | None]:
        if self.counterparty_id:
            return self.counterparty_id, self.primary_reason
        if self.extracted_counterparty and norm(self.extracted_counterparty):
            return "x:" + norm(self.extracted_counterparty), self.primary_reason
        return "solo:" + self.id, self.primary_reason


@dataclass
class Cluster:
    docs: list[Doc] = field(default_factory=list)

    @property
    def amount(self) -> Decimal:
        return sum((d.amount for d in self.docs if d.amount is not None), Decimal(0))


def load_docs(conn: Connection, ids: Iterable[str]) -> list[Doc]:
    """The candidate facts C6 reads: document, current classification, extracted counterparty."""
    ids = list(ids)
    if not ids:
        return []
    d, c, cp, r = T["documents"], T["classifications"], T["counterparties"], T["rules"]
    ef, e = T["extraction_fields"], T["entities"]
    extracted = (
        select(ef.c.value)
        .where(ef.c.extraction_id == d.c.extraction_id, ef.c.key == "counterparty")
        .scalar_subquery()
    )
    rows = conn.execute(
        select(
            d,
            cp.c.name.label("cp_name"),
            extracted.label("extracted_cp"),
            e.c.key.label("cls_entity"),
            c.c.category_id.label("cls_category"),
            c.c.subcategory_key.label("cls_sub"),
            c.c.confidence.label("cls_confidence"),
            r.c.action.label("rule_action"),
        )
        .outerjoin(cp, cp.c.id == d.c.counterparty_id)
        .outerjoin(c, c.c.id == d.c.classification_id)
        .outerjoin(e, e.c.id == func.coalesce(c.c.entity_id, d.c.entity_id))
        .outerjoin(r, r.c.id == func.coalesce(c.c.rule_id, d.c.rule_id))
        .where(d.c.id.in_(ids))
    ).mappings()
    out = []
    for row in rows:
        reasons = list(row["reasons"])
        asked = reasons == ["low"] and bool((row["rule_action"] or {}).get("review"))
        out.append(
            Doc(
                id=row["id"],
                sha256=row["sha256"],
                arrived_at=row["arrived_at"],
                batch_id=row["batch_id"],
                status=row["status"],
                reasons=reasons,
                title=row["title"] or row["original_name"],
                counterparty_id=row["counterparty_id"],
                counterparty=row["cp_name"],
                extracted_counterparty=row["extracted_cp"],
                doc_type=row["doc_type"],
                doc_date=row["doc_date"],
                amount=row["amount"],
                currency=row["currency"],
                addressee=row["addressee"],
                extraction_id=row["extraction_id"],
                entity=row["cls_entity"],
                category=row["cls_category"] or row["category_id"],
                subcategory=row["cls_sub"] if row["cls_category"] else row["subcategory_key"],
                confidence=row["cls_confidence"]
                if row["cls_confidence"] is not None
                else row["confidence"],
                asked_only=asked,
            )
        )
    order = {i: n for n, i in enumerate(ids)}
    return sorted(out, key=lambda x: order[x.id])


def clusters(docs: Iterable[Doc]) -> list[Cluster]:
    """§4.2: by (counterparty, primary reason); largest first, then by amount."""
    by_key: dict[tuple[str, str | None], Cluster] = {}
    for doc in sorted(docs, key=lambda x: (x.arrived_at, x.id)):
        by_key.setdefault(doc.cluster_key, Cluster()).docs.append(doc)
    return sorted(
        by_key.values(),
        key=lambda c: (-len(c.docs), -c.amount, c.docs[0].arrived_at, c.docs[0].id),
    )


def _eligible(conn: Connection, scope: Mapping[str, Any]) -> list[str]:
    d, b = T["documents"], T["batches"]
    kind = scope["type"]
    statuses = ("review", "filed") if kind == "documents" else ("review",)
    q = (
        select(d.c.id)
        .join(b, b.c.id == d.c.batch_id)
        .where(d.c.deleted_at.is_(None), d.c.status.in_(statuses), b.c.visitor.is_(False))
    )
    if kind == "batch":
        q = q.where(d.c.batch_id == scope["batch_id"])
    elif kind == "counterparty":
        q = q.where(d.c.counterparty_id == scope["counterparty_id"])
    elif kind == "documents":
        q = q.where(d.c.id.in_(scope["document_ids"]))
    return list(conn.execute(q).scalars())


def is_candidate(doc: Doc) -> bool:
    """§2.2 rule 2: nothing to ask about an unreadable page or a rule's own `review: true`."""
    return doc.reasons != ["unreadable"] and not doc.asked_only


def capped(docs: list[Doc], limit: int = MAX_CANDIDATES) -> list[Doc]:
    """At most `limit`: the largest clusters first, then the oldest arrivals."""
    flat = [doc for c in clusters(docs) for doc in c.docs]
    return flat[:limit]


def candidates(conn: Connection, scope: Mapping[str, Any], *, cap: bool = True) -> list[Doc]:
    """§2.2 candidates of a document scope, sorted by id; capped unless `cap` is false."""
    docs = [x for x in load_docs(conn, _eligible(conn, scope)) if is_candidate(x)]
    return sorted(capped(docs) if cap else docs, key=lambda x: x.id)


def snapshot(docs: list[Doc]) -> list[str]:
    """The `candidate_document_ids` of a new interview: capped, sorted by id."""
    return sorted(d.id for d in capped(docs))


def covered(conn: Connection) -> set[str]:
    """§3.3: documents in any question, or in the snapshot of a generating interview."""
    q, i = T["interview_questions"], T["interviews"]
    asked = conn.execute(select(func.unnest(q.c.affected_document_ids))).scalars()
    pending = conn.execute(
        select(func.jsonb_array_elements_text(i.c.scope["candidate_document_ids"])).where(
            i.c.status == "generating", i.c.scope.has_key("candidate_document_ids")
        )
    ).scalars()
    return set(asked) | set(pending)


def seed_candidates(conn: Connection) -> list[str]:
    """§2.2 Seed: seed counterparties of the listed kinds no active rule names, at most 7."""
    cp, a, r = T["counterparties"], T["counterparty_aliases"], T["rules"]
    rows = list(
        conn.execute(
            select(cp.c.id, cp.c.key, cp.c.name_norm)
            .where(cp.c.origin == "seed", cp.c.kind.in_(SEED_KINDS))
            .order_by(cp.c.name_norm, cp.c.id)
        ).mappings()
    )
    aliases: dict[str, set[str]] = {}
    for x in conn.execute(select(a.c.counterparty_id, a.c.alias_norm)):
        aliases.setdefault(x.counterparty_id, set()).add(x.alias_norm)
    named: set[str] = set()
    for conditions in conn.execute(select(r.c.conditions).where(r.c.state == "active")).scalars():
        for c in conditions:
            if c.get("field") == "counterparty" and c.get("op") == "equals":
                named.add(norm(str(c.get("value", ""))))
    out = []
    for row in rows:
        names = {norm(row["key"]), row["name_norm"], *aliases.get(row["id"], ())}
        if not names & named:
            out.append(row["id"])
    return out[:MAX_SEED_COUNTERPARTIES]


def seed_documents(conn: Connection, counterparty_id: str, limit: int = 3) -> list[str]:
    d = T["documents"]
    return list(
        conn.execute(
            select(d.c.id)
            .where(d.c.counterparty_id == counterparty_id, d.c.deleted_at.is_(None))
            .order_by(d.c.arrived_at.desc(), d.c.id)
            .limit(limit)
        ).scalars()
    )


def scope_equal(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    """§2.3: the candidate snapshot plays no part."""
    if a["type"] != b["type"]:
        return False
    match a["type"]:
        case "batch":
            return a["batch_id"] == b["batch_id"]
        case "counterparty":
            return a["counterparty_id"] == b["counterparty_id"]
        case "documents":
            return sorted(a["document_ids"]) == sorted(b["document_ids"])
    return True


def scope_filter(scope: Mapping[str, Any]) -> Any:
    """A SQL prefilter on `interviews.scope` for equal scopes (§2.3)."""
    i = T["interviews"]
    clause = i.c.scope["type"].astext == scope["type"]
    for key in ("batch_id", "counterparty_id"):
        if key in scope:
            clause = clause & (i.c.scope[key].astext == scope[key])
    return clause


def open_question_count() -> Any:
    q, i = T["interview_questions"], T["interviews"]
    return (
        select(func.count(q.c.id))
        .where(q.c.interview_id == i.c.id, q.c.status == "open")
        .scalar_subquery()
    )


def reusable_clause() -> Any:
    """§2.3: `generating`, or `ready` with at least one open question."""
    i = T["interviews"]
    return or_(i.c.status == "generating", (i.c.status == "ready") & (open_question_count() > 0))

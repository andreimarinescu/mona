"""C4 §3 common filter parameters: resolution and the SQL they become."""

from datetime import date
from typing import Annotated, Any, Literal

from pydantic import Field
from sqlalchemy import extract, func, select
from sqlalchemy.ext.asyncio import AsyncConnection

from mona.db.models import Category, Counterparty, CounterpartyAlias, Document, Entity
from mona.mcp.core import Scope, ToolFailure
from mona.text import contains_word, norm

TRIGRAM_MIN = 0.5

EntityParam = Annotated[
    str | None,
    Field(min_length=1, max_length=160, description="Entity key, name, folder name or alias."),
]
CategoryParam = Annotated[
    str | None, Field(min_length=1, max_length=160, description="Category id or label.")
]
CounterpartyParam = Annotated[
    str | None,
    Field(min_length=1, max_length=160, description="Counterparty name or alias, e.g. AGIPI."),
]
YearParam = Annotated[int | None, Field(ge=2000, le=2100, description="Year of the document date.")]
FiscalYearParam = Annotated[int | None, Field(ge=2000, le=2100)]
AmountParam = Annotated[float | None, Field(ge=0)]
StatusParam = Literal["filed", "review", "any"]
LimitParam = Annotated[int, Field(ge=1, le=25)]
CursorParam = Annotated[str | None, Field(min_length=1, max_length=200)]

STATUSES = {
    "filed": ("filed",),
    "review": ("review", "unreadable"),
    "any": ("filed", "review", "unreadable"),
}


def ref(key: str, name: str) -> dict[str, str]:
    return {"key": key, "name": name}


async def visible_entities(scope: Scope) -> list[Any]:
    rows = (
        await scope.conn.execute(
            select(
                Entity.id,
                Entity.key,
                Entity.display_name,
                Entity.folder_name,
                Entity.aliases,
                Entity.purge_after_hours,
            ).order_by(Entity.sort_order, Entity.key)
        )
    ).all()
    return [r for r in rows if scope.entity_visible(r.id)]


async def resolve_entity(scope: Scope, value: str) -> Any:
    """`norm()` equality with key, name, folder or alias; else one trigram match ≥ 0.5."""
    entities = await visible_entities(scope)
    wanted = norm(value)
    exact = {
        e.id: e
        for e in entities
        if wanted in {norm(x) for x in (e.key, e.display_name, e.folder_name, *e.aliases)}
    }
    if len(exact) == 1:
        return next(iter(exact.values()))
    if not exact and entities:
        scores = (
            await scope.conn.execute(
                select(*(func.similarity(wanted, norm(e.display_name)) for e in entities))
            )
        ).one()
        close = [e for e, s in zip(entities, scores, strict=True) if s >= TRIGRAM_MIN]
        if len(close) == 1:
            return close[0]
    raise ToolFailure(
        "invalid_argument",
        f"Unknown entity '{value}'.",
        hint="Use one of the valid values.",
        field="entity",
        valid=[ref(e.key, e.display_name) for e in entities if e.purge_after_hours is None],
    )


async def categories(conn: AsyncConnection) -> list[Any]:
    return (
        await conn.execute(
            select(Category.id, Category.labels).order_by(Category.sort_order, Category.id)
        )
    ).all()


def category_ref(category_id: str | None, labels: dict[str, str] | None) -> dict | None:
    if category_id is None:
        return None
    return {"id": category_id, "label": (labels or {}).get("en", category_id)}


async def resolve_category(conn: AsyncConnection, value: str) -> str:
    rows = await categories(conn)
    wanted = norm(value)
    for r in rows:
        if wanted == norm(r.id) or wanted in {norm(v) for v in r.labels.values()}:
            return r.id
    raise ToolFailure(
        "invalid_argument",
        f"Unknown category '{value}'.",
        hint="Use one of the valid values.",
        field="category",
        valid=[category_ref(r.id, r.labels) for r in rows][:30],
    )


async def matching_counterparties(conn: AsyncConnection, value: str) -> list[str]:
    """Counterparties whose name or an alias whole-word contains `norm(value)` (C5 §2)."""
    wanted = norm(value)
    if not wanted:
        return []
    names = (await conn.execute(select(Counterparty.id, Counterparty.name_norm))).all()
    aliases = (
        await conn.execute(select(CounterpartyAlias.counterparty_id, CounterpartyAlias.alias_norm))
    ).all()
    hits = {cid for cid, n in names if contains_word(n, wanted)}
    hits |= {cid for cid, a in aliases if contains_word(a, wanted)}
    return sorted(hits)


FILTER_KEYS = (
    "entity",
    "category",
    "counterparty",
    "year",
    "fiscal_year",
    "date_from",
    "date_to",
    "amount_min",
    "amount_max",
)


async def document_clauses(
    scope: Scope,
    *,
    entity: str | None = None,
    category: str | None = None,
    counterparty: str | None = None,
    year: int | None = None,
    fiscal_year: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    amount_min: float | None = None,
    amount_max: float | None = None,
    status: str = "any",
) -> list[Any] | None:
    """WHERE clauses for the common filters; None when the counterparty matches nothing."""
    clauses: list[Any] = [
        Document.deleted_at.is_(None),
        Document.status.in_(STATUSES[status]),
        scope.visible_entity_clause(Document.entity_id),
    ]
    if entity is not None:
        clauses.append(Document.entity_id == (await resolve_entity(scope, entity)).id)
    if category is not None:
        clauses.append(Document.category_id == await resolve_category(scope.conn, category))
    if counterparty is not None:
        ids = await matching_counterparties(scope.conn, counterparty)
        if not ids:
            return None
        clauses.append(Document.counterparty_id.in_(ids))
    if year is not None:
        clauses.append(extract("year", Document.doc_date) == year)
    if fiscal_year is not None:
        clauses.append(Document.fiscal_year == fiscal_year)
    if date_from is not None:
        clauses.append(Document.doc_date >= date_from)
    if date_to is not None:
        clauses.append(Document.doc_date <= date_to)
    if amount_min is not None:
        clauses.append(Document.amount >= amount_min)
    if amount_max is not None:
        clauses.append(Document.amount <= amount_max)
    return clauses

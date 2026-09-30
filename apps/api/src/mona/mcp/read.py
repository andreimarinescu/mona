"""The read-only tools (C4 §3.1–§3.4, §3.10, §3.15)."""

from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any, Literal

from pydantic import Field
from sqlalchemy import and_, any_, false, func, select
from sqlalchemy.orm import aliased

from mona import clock
from mona.db import get_engine
from mona.db.models import (
    Category,
    Classification,
    Counterparty,
    Deadline,
    Document,
    Entity,
    ExtractionField,
    FileOp,
    Interview,
    InterviewQuestion,
    Reminder,
    Rule,
    Subcategory,
    SubUnit,
)
from mona.mcp.core import (
    DEFAULT_LIMIT,
    PLACEHOLDER_REF,
    Scope,
    ToolFailure,
    channel,
    clip,
    decode_cursor,
    encode_cursor,
    fit,
    not_found,
    rule_visibility,
    scope_for,
    tool,
    write_cards,
)
from mona.mcp.filters import (
    AmountParam,
    CategoryParam,
    CounterpartyParam,
    CursorParam,
    EntityParam,
    FiscalYearParam,
    LimitParam,
    StatusParam,
    YearParam,
    category_ref,
    document_clauses,
    ref,
    resolve_entity,
)
from mona.text import norm

DocIdParam = Annotated[str, Field(pattern=r"^doc_[0-9a-hjkmnp-tv-z]{26}$")]

SEARCH_CARDS, SUM_CARDS, QUEUE_CARDS, DEADLINE_CARDS = 3, 5, 3, 5
BRIEF_DUE_DAYS, BRIEF_DUE_MAX, BRIEF_LEARNED_MAX = 7, 5, 10


def _num(value: Any) -> float | None:
    return float(value) if value is not None else None


def _day(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _ts(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _entity(row: Any) -> dict | None:
    return ref(row.entity_key, row.entity_name) if row.entity_key else None


def _page(result: dict, key: str, *, offset: int, total: int, params: dict, carded: bool) -> dict:
    """Fits a list page (§2.3) with room for the card refs and cursor it will carry."""
    items = result[key]
    result["next_cursor"] = encode_cursor(offset + len(items), params)
    result["card_refs"] = [PLACEHOLDER_REF] * (len(items) if carded else 0)
    fit(result, key)
    shown = offset + len(items)
    result["next_cursor"] = encode_cursor(shown, params) if shown < total else None
    return result


def _summary_columns() -> list[Any]:
    return [
        Document.id,
        func.coalesce(Document.title, Document.original_name).label("title"),
        Entity.key.label("entity_key"),
        Entity.display_name.label("entity_name"),
        Document.category_id,
        Category.labels.label("category_labels"),
        Counterparty.name.label("counterparty"),
        Document.doc_date,
        Document.amount,
        Document.currency,
        Document.due_date,
        Document.status,
    ]


def _joined(stmt: Any) -> Any:
    return (
        stmt.outerjoin(Entity, Entity.id == Document.entity_id)
        .outerjoin(Category, Category.id == Document.category_id)
        .outerjoin(Counterparty, Counterparty.id == Document.counterparty_id)
    )


def _summary(r: Any) -> dict:
    return {
        "id": r.id,
        "title": clip(r.title),
        "entity": _entity(r),
        "category": category_ref(r.category_id, r.category_labels),
        "counterparty": r.counterparty,
        "date": _day(r.doc_date),
        "amount": _num(r.amount),
        "currency": r.currency,
        "due_date": _day(r.due_date),
        "status": r.status,
    }


@tool(
    "Search the practice's archive. Filter by entity, category, counterparty, year or fiscal "
    "year, date range and amount range; add a free-text query for words in the documents. "
    "Results already include title, entity, category, counterparty, date, amount and status, "
    "so call get_document only when you need a field not listed here. If you need a total, "
    "call sum_amounts with the same filters instead of summing yourself. Up to three results "
    "are shown to the person as document cards."
)
async def search_documents(
    query: Annotated[str | None, Field(min_length=1, max_length=200)] = None,
    entity: EntityParam = None,
    category: CategoryParam = None,
    counterparty: CounterpartyParam = None,
    year: YearParam = None,
    fiscal_year: FiscalYearParam = None,
    date_from: date | None = None,
    date_to: date | None = None,
    amount_min: AmountParam = None,
    amount_max: AmountParam = None,
    status: StatusParam = "any",
    limit: LimitParam = DEFAULT_LIMIT,
    cursor: CursorParam = None,
) -> dict:
    filters = dict(
        entity=entity,
        category=category,
        counterparty=counterparty,
        year=year,
        fiscal_year=fiscal_year,
        date_from=date_from,
        date_to=date_to,
        amount_min=amount_min,
        amount_max=amount_max,
        status=status,
    )
    params = {**filters, "query": query}
    async with get_engine().begin() as conn:
        scope = await scope_for(conn, channel())
        offset = decode_cursor(cursor, params)
        clauses = await document_clauses(scope, **filters)
        if clauses is None:
            return {"total": 0, "next_cursor": None, "results": [], "card_refs": []}
        order: list[Any] = [Document.doc_date.desc().nulls_last(), Document.id]
        if query is not None:
            tsq = func.websearch_to_tsquery("mona", norm(query))
            clauses.append(Document.fts.op("@@")(tsq))
            order = [func.ts_rank(Document.fts, tsq).desc(), *order]
        total = (
            await conn.execute(select(func.count()).select_from(Document).where(*clauses))
        ).scalar_one()
        rows = (
            await conn.execute(
                _joined(select(*_summary_columns()).select_from(Document))
                .where(*clauses)
                .order_by(*order)
                .offset(offset)
                .limit(limit)
            )
        ).all()
        carded = 1 <= total <= SEARCH_CARDS
        result = _page(
            {"total": total, "next_cursor": None, "results": [_summary(r) for r in rows]},
            "results",
            offset=offset,
            total=total,
            params=params,
            carded=carded,
        )
        result["card_refs"] = await write_cards(
            scope,
            "search_documents",
            [("doc", {"document_id": r["id"]}) for r in result["results"]] if carded else [],
        )
        return result


@tool(
    "Get one document's facts: fields with whether each was verified on the page, where it is "
    "filed, the rule that filed it, and its deadlines. Use it when the person asks about a "
    "specific document or you need a field the search results don't have. Shows the document "
    "as a card."
)
async def get_document(document_id: DocIdParam) -> dict:
    async with get_engine().begin() as conn:
        scope = await scope_for(conn, channel())
        sub = aliased(Subcategory)
        row = (
            await conn.execute(
                _joined(
                    select(
                        Document,
                        func.coalesce(Document.title, Document.original_name).label("shown"),
                        Entity.key.label("entity_key"),
                        Entity.display_name.label("entity_name"),
                        Category.labels.label("category_labels"),
                        sub.labels.label("sub_labels"),
                        SubUnit.label.label("unit_label"),
                        Counterparty.name.label("counterparty_name"),
                        Rule.name.label("rule_name"),
                    ).select_from(Document)
                )
                .outerjoin(
                    sub,
                    and_(
                        sub.category_id == Document.category_id,
                        sub.key == Document.subcategory_key,
                    ),
                )
                .outerjoin(SubUnit, SubUnit.id == Document.sub_unit_id)
                .outerjoin(Rule, Rule.id == Document.rule_id)
                .where(
                    Document.id == document_id,
                    Document.deleted_at.is_(None),
                    scope.visible_entity_clause(Document.entity_id),
                )
            )
        ).first()
        if row is None:
            raise not_found("document")
        d = row
        unverified = (
            (
                await conn.execute(
                    select(ExtractionField.key)
                    .where(
                        ExtractionField.extraction_id == d.extraction_id,
                        ExtractionField.verified.is_(False),
                    )
                    .order_by(ExtractionField.key)
                )
            )
            .scalars()
            .all()
            if d.extraction_id
            else []
        )
        deadline_ids = (
            (
                await conn.execute(
                    select(Deadline.id)
                    .where(Deadline.document_id == d.id)
                    .order_by(Deadline.due_date, Deadline.id)
                )
            )
            .scalars()
            .all()
        )
        result = {
            "id": d.id,
            "title": clip(row.shown),
            "status": d.status,
            "entity": _entity(row),
            "sub_unit": row.unit_label,
            "category": category_ref(d.category_id, row.category_labels),
            "subcategory": (row.sub_labels or {}).get("en") if row.sub_labels else None,
            "counterparty": row.counterparty_name,
            "issuer": clip(d.issuer),
            "reference": clip(d.reference),
            "doc_type": clip(d.doc_type),
            "doc_date": _day(d.doc_date),
            "period_start": _day(d.period_start),
            "period_end": _day(d.period_end),
            "fiscal_year": d.fiscal_year,
            "amount": _num(d.amount),
            "currency": d.currency,
            "due_date": _day(d.due_date),
            "addressee": clip(d.addressee),
            "path": clip(d.current_path, 400),
            "filed_by": d.filed_by,
            "filed_at": _ts(d.filed_at),
            "rule": {"id": d.rule_id, "name": row.rule_name} if d.rule_id else None,
            "confidence": d.confidence,
            "band": d.band,
            "reasons": list(d.reasons),
            "unverified_fields": list(unverified),
            "deadline_ids": list(deadline_ids),
            "page_count": d.page_count,
        }
        result["card_refs"] = await write_cards(
            scope, "get_document", [("doc", {"document_id": d.id})]
        )
        return result


@tool(
    "Add up document amounts, either for a list of document ids or for the same filters as "
    "search_documents (entity, category, counterparty, year, fiscal year, dates, amounts). One "
    "call answers 'how much did we pay X in 2025'. Amounts are what the documents state (billed "
    "or due); the archive doesn't record whether they were paid, so say so when it matters. "
    "Documents without an amount are listed as excluded. Up to five documents are shown as cards."
)
async def sum_amounts(
    document_ids: Annotated[list[DocIdParam] | None, Field(min_length=1, max_length=100)] = None,
    entity: EntityParam = None,
    category: CategoryParam = None,
    counterparty: CounterpartyParam = None,
    year: YearParam = None,
    fiscal_year: FiscalYearParam = None,
    date_from: date | None = None,
    date_to: date | None = None,
    amount_min: AmountParam = None,
    amount_max: AmountParam = None,
) -> dict:
    filters = dict(
        entity=entity,
        category=category,
        counterparty=counterparty,
        year=year,
        fiscal_year=fiscal_year,
        date_from=date_from,
        date_to=date_to,
        amount_min=amount_min,
        amount_max=amount_max,
    )
    has_filter = any(v is not None for v in filters.values())
    if (document_ids is None) == (not has_filter):
        raise ToolFailure(
            "invalid_argument",
            "Pass either document_ids or at least one filter, not both.",
            field="document_ids",
        )
    async with get_engine().begin() as conn:
        scope = await scope_for(conn, channel())
        clauses = await document_clauses(scope, **filters)
        excluded: list[dict] = []
        if clauses is None:
            clauses = [false()]
        if document_ids is not None:
            wanted = list(dict.fromkeys(document_ids))
            clauses.append(Document.id.in_(wanted))
        rows = (
            await conn.execute(
                select(Document.id, Document.amount, Document.currency, Document.doc_date).where(
                    *clauses
                )
            )
        ).all()
        if document_ids is not None:
            found = {r.id: r for r in rows}
            rows = [found[i] for i in wanted if i in found]
            excluded += [{"id": i, "reason": "not_found"} for i in wanted if i not in found]
        else:
            rows.sort(key=lambda r: (r.doc_date is None, -(r.doc_date or date.min).toordinal()))
        summed = [r for r in rows if r.amount is not None and r.currency in ("EUR", "RON")]
        excluded += [
            {"id": r.id, "reason": "no_amount" if r.amount is None else "other_currency"}
            for r in rows
            if r not in summed
        ]
        totals = (
            await conn.execute(
                select(Document.currency, func.sum(Document.amount))
                .where(Document.id.in_([r.id for r in summed]))
                .group_by(Document.currency)
                .order_by(Document.currency)
            )
        ).all()
        listed = [r.id for r in summed][:25]
        carded = 1 <= len(summed) <= SUM_CARDS
        return {
            "count": len(summed),
            "totals": [{"currency": c, "total": float(t)} for c, t in totals],
            "document_ids": listed,
            "listed": len(listed),
            "excluded": excluded[:10],
            "card_refs": await write_cards(
                scope,
                "sum_amounts",
                [("doc", {"document_id": r.id}) for r in summed] if carded else [],
            ),
        }


@tool(
    "List documents waiting for the person's review, with why each is waiting (low "
    "confidence, unknown entity, conflicting rules, unreadable) and your current suggestion. "
    "Use it for 'what needs my attention'. Up to three are shown as cards; the Review page has "
    "the rest."
)
async def list_review_queue(
    reason: Literal["low", "entity", "conflict", "unreadable"] | None = None,
    limit: LimitParam = DEFAULT_LIMIT,
    cursor: CursorParam = None,
) -> dict:
    params = {"reason": reason}
    async with get_engine().begin() as conn:
        scope = await scope_for(conn, channel())
        offset = decode_cursor(cursor, params)
        sugg_entity = aliased(Entity)
        sugg_category = aliased(Category)
        clauses = [
            Document.deleted_at.is_(None),
            Document.status.in_(("review", "unreadable")),
            scope.visible_entity_clause(Document.entity_id),
            scope.visible_entity_clause(Classification.entity_id),
        ]
        if reason is not None:
            clauses.append(any_(Document.reasons) == reason)
        total = (
            await conn.execute(
                select(func.count())
                .select_from(Document)
                .outerjoin(Classification, Classification.id == Document.classification_id)
                .where(*clauses)
            )
        ).scalar_one()
        rows = (
            await conn.execute(
                select(
                    Document.id,
                    func.coalesce(Document.title, Document.original_name).label("title"),
                    Document.reasons,
                    Document.arrived_at,
                    sugg_entity.key.label("entity_key"),
                    sugg_entity.display_name.label("entity_name"),
                    sugg_category.id.label("category_id"),
                    sugg_category.labels.label("category_labels"),
                    func.coalesce(Classification.confidence, Document.confidence).label("conf"),
                )
                .select_from(Document)
                .outerjoin(Classification, Classification.id == Document.classification_id)
                .outerjoin(
                    sugg_entity,
                    sugg_entity.id == func.coalesce(Classification.entity_id, Document.entity_id),
                )
                .outerjoin(
                    sugg_category,
                    sugg_category.id
                    == func.coalesce(Classification.category_id, Document.category_id),
                )
                .where(*clauses)
                .order_by(Document.arrived_at, Document.id)
                .offset(offset)
                .limit(limit)
            )
        ).all()
        items = [
            {
                "document_id": r.id,
                "title": clip(r.title),
                "reasons": list(r.reasons),
                "suggestion": {
                    "entity": _entity(r),
                    "category": category_ref(r.category_id, r.category_labels),
                    "confidence": r.conf,
                },
                "arrived_at": _ts(r.arrived_at),
            }
            for r in rows
        ]
        carded = 1 <= total <= QUEUE_CARDS
        result = _page(
            {"total": total, "next_cursor": None, "items": items},
            "items",
            offset=offset,
            total=total,
            params=params,
            carded=carded,
        )
        result["card_refs"] = await write_cards(
            scope,
            "list_review_queue",
            [("doc", {"document_id": i["document_id"]}) for i in result["items"]] if carded else [],
        )
        return result


def _deadline_query(scope: Scope, *clauses: Any) -> Any:
    return (
        select(
            Deadline.id,
            Deadline.document_id,
            Deadline.label,
            Deadline.due_date,
            Deadline.amount,
            Deadline.currency,
            Deadline.status,
            Entity.key.label("entity_key"),
            Entity.display_name.label("entity_name"),
        )
        .join(Entity, Entity.id == Deadline.entity_id)
        .outerjoin(Document, Document.id == Deadline.document_id)
        .where(
            Deadline.status == "open",
            Document.deleted_at.is_(None),
            scope.visible_entity_clause(Deadline.entity_id),
            *clauses,
        )
    )


@tool(
    "List upcoming payment and reply deadlines with amount, entity and days left, including "
    "overdue ones. Use it for 'what's due'. Up to five are shown as cards."
)
async def list_deadlines(
    within_days: Annotated[int, Field(ge=0, le=366)] = 30,
    entity: EntityParam = None,
    include_overdue: bool = True,
    limit: LimitParam = DEFAULT_LIMIT,
    cursor: CursorParam = None,
) -> dict:
    params = {"within_days": within_days, "entity": entity, "include_overdue": include_overdue}
    today = clock.paris_today()
    async with get_engine().begin() as conn:
        scope = await scope_for(conn, channel())
        offset = decode_cursor(cursor, params)
        clauses: list[Any] = [Deadline.due_date <= today + timedelta(days=within_days)]
        if not include_overdue:
            clauses.append(Deadline.due_date >= today)
        if entity is not None:
            clauses.append(Deadline.entity_id == (await resolve_entity(scope, entity)).id)
        query = _deadline_query(scope, *clauses)
        total = (
            await conn.execute(select(func.count()).select_from(query.subquery()))
        ).scalar_one()
        rows = (
            await conn.execute(
                query.order_by(Deadline.due_date, Deadline.id).offset(offset).limit(limit)
            )
        ).all()
        reminders = await _next_reminders(conn, [r.id for r in rows])
        items = [
            {
                "deadline_id": r.id,
                "document_id": r.document_id,
                "label": clip(r.label),
                "entity": _entity(r),
                "due_date": _day(r.due_date),
                "days_left": (r.due_date - today).days,
                "amount": _num(r.amount),
                "currency": r.currency,
                "status": r.status,
                "reminder_on": _day(reminders.get(r.id)),
            }
            for r in rows
        ]
        carded = 1 <= total <= DEADLINE_CARDS
        result = _page(
            {"total": total, "next_cursor": None, "items": items},
            "items",
            offset=offset,
            total=total,
            params=params,
            carded=carded,
        )
        result["card_refs"] = await write_cards(
            scope,
            "list_deadlines",
            [("deadline", {"deadline_id": i["deadline_id"]}) for i in result["items"]]
            if carded
            else [],
        )
        return result


async def _next_reminders(conn: Any, deadline_ids: list[str]) -> dict[str, date]:
    if not deadline_ids:
        return {}
    rows = (
        await conn.execute(
            select(Reminder.deadline_id, func.min(Reminder.remind_on))
            .where(Reminder.deadline_id.in_(deadline_ids), Reminder.status == "scheduled")
            .group_by(Reminder.deadline_id)
        )
    ).all()
    return dict(rows)


@tool(
    "Get the facts for the morning brief: what was filed in the last 24 hours (or since a time "
    "you pass), what needs review, what is due soon, what you learned, and pending questions. "
    "Write the brief from these facts, amounts and due dates first, one short paragraph."
)
async def get_brief(since: datetime | None = None) -> dict:
    now = clock.now()
    if since is None:
        since = now - timedelta(hours=24)
    elif since.tzinfo is None:
        since = since.replace(tzinfo=UTC)
    today = clock.paris_today(now)
    async with get_engine().connect() as conn:
        scope = await scope_for(conn, channel())
        filed = (
            await conn.execute(
                select(Entity.key, Entity.display_name, func.count(Document.id))
                .select_from(Document)
                .join(Entity, Entity.id == Document.entity_id)
                .where(
                    Document.status == "filed",
                    Document.deleted_at.is_(None),
                    Document.filed_at >= since,
                    Document.filed_at <= now,
                    scope.visible_entity_clause(Document.entity_id),
                )
                .group_by(Entity.key, Entity.display_name, Entity.sort_order)
                .order_by(func.count(Document.id).desc(), Entity.sort_order)
            )
        ).all()
        review = (
            await conn.execute(
                select(Document.reasons).where(
                    Document.deleted_at.is_(None),
                    Document.status.in_(("review", "unreadable")),
                    scope.visible_entity_clause(Document.entity_id),
                )
            )
        ).scalars()
        review = list(review)
        by_reason: dict[str, int] = {}
        for reasons in review:
            for reason in reasons:
                by_reason[reason] = by_reason.get(reason, 0) + 1
        due = (
            await conn.execute(
                _deadline_query(scope, Deadline.due_date <= today + timedelta(days=BRIEF_DUE_DAYS))
                .order_by(Deadline.due_date, Deadline.id)
                .limit(BRIEF_DUE_MAX)
            )
        ).all()
        reminders = (
            await conn.execute(
                select(
                    Reminder.id,
                    Reminder.note,
                    func.coalesce(Deadline.label, Document.title, Document.original_name).label(
                        "label"
                    ),
                )
                .outerjoin(Deadline, Deadline.id == Reminder.deadline_id)
                .outerjoin(
                    Document,
                    Document.id == func.coalesce(Reminder.document_id, Deadline.document_id),
                )
                .where(
                    Reminder.status == "scheduled",
                    Reminder.remind_on == today,
                    Document.deleted_at.is_(None),
                    scope.visible_entity_clause(Deadline.entity_id),
                    scope.visible_entity_clause(Document.entity_id),
                )
                .order_by(Reminder.created_at, Reminder.id)
            )
        ).all()
        fired = (
            select(func.count(func.distinct(FileOp.document_id)))
            .where(FileOp.rule_id == Rule.id, FileOp.at >= since, FileOp.fs_state == "done")
            .scalar_subquery()
        )
        learned_rows = (
            await conn.execute(
                select(Rule.id, Rule.name, Rule.created_at, Rule.conditions, Rule.action, fired)
                .where(
                    Rule.source != "seed",
                    Rule.state == "active",
                    Rule.created_at >= since,
                )
                .order_by(Rule.created_at, Rule.id)
            )
        ).all()
        rules_seen = await rule_visibility(scope)
        learned = [
            {
                "rule_id": r.id,
                "name": clip(r.name),
                "created_at": _ts(r.created_at),
                "fired_since": r[5],
            }
            for r in learned_rows
            if rules_seen is None or rules_seen.visible(r.conditions, r.action)
        ][:BRIEF_LEARNED_MAX]
        open_questions = (
            select(func.count(InterviewQuestion.id))
            .where(
                InterviewQuestion.interview_id == Interview.id,
                InterviewQuestion.status == "open",
            )
            .scalar_subquery()
        )
        pending = (
            await conn.execute(
                select(Interview.id, open_questions.label("n"))
                .where(Interview.status == "ready", open_questions > 0)
                .order_by(Interview.created_at.desc(), Interview.id.desc())
                .limit(1)
            )
        ).first()
    return fit(
        {
            "generated_at": _ts(now),
            "since": _ts(since),
            "filed": {
                "count": sum(n for _, _, n in filed),
                "by_entity": [{"key": k, "name": name, "count": n} for k, name, n in filed],
            },
            "needs_review": {"count": len(review), "by_reason": by_reason},
            "due_soon": [
                {
                    "deadline_id": r.id,
                    "label": clip(r.label),
                    "entity": _entity(r),
                    "due_date": _day(r.due_date),
                    "days_left": (r.due_date - today).days,
                    "amount": _num(r.amount),
                    "currency": r.currency,
                }
                for r in due
            ],
            "reminders_today": [
                {"reminder_id": r.id, "label": clip(r.label), "note": clip(r.note)}
                for r in reminders
            ],
            "learned": learned,
            "pending_interview": (
                {"interview_id": pending.id, "open_questions": pending.n} if pending else None
            ),
        },
        "learned",
    )

"""C2 §4 documents (search, detail, files, folders) and §6 review and document actions."""

import logging
from collections.abc import Mapping
from datetime import date
from typing import Annotated, Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import FileResponse
from sqlalchemy import Connection, any_, extract, func, select, update

from mona import clock
from mona.api import views
from mona.api.deps import CtxDep, Lang, Offset, Page, PageLimit, body_id, path_id, polled, run
from mona.api.errors import ApiFailure, errors
from mona.api.models import (
    ConversationRef,
    CorrectionRequest,
    CounterpartyById,
    DeleteRequest,
    DocumentPage,
    FileOpResult,
    FolderListing,
    LikeThisResult,
)
from mona.db import get_sync_engine
from mona.dto.models import DocumentDetail, DocumentSummary
from mona.fileops import Change, FileOpError, inbox_name, resolve_inside
from mona.rules import store
from mona.services import Ctx, correct_document, registry
from mona.services.registry import T
from mona.services.rules import draft_from_correction, preview_rule
from mona.text import norm

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["documents"])

DocId = path_id("doc", "id")
Status = Literal["filed", "review", "unreadable"]
Sort = Literal["relevance", "date_desc", "date_asc", "arrived_desc", "amount_desc"]
LISTED = ("filed", "review", "unreadable")
TOP_COUNTERPARTIES = 20
FILE_HEADERS = {"X-Content-Type-Options": "nosniff", "Cache-Control": "private"}


def _conn() -> Connection:
    return get_sync_engine().connect()


# --- §4.1 archive search ---


def _search(conn: Connection, lang: str, p: dict[str, Any]) -> dict[str, Any]:
    d, e, c, cp = T["documents"], T["entities"], T["categories"], T["counterparties"]
    base = [d.c.deleted_at.is_(None), d.c.status.in_(LISTED)]
    f: dict[str, list[Any]] = {"status": [d.c.status.in_(p["status"] or LISTED)]}
    if p["entity_id"]:
        f["entity"] = [d.c.entity_id == p["entity_id"]]
    if p["category_id"]:
        f["category"] = [d.c.category_id == p["category_id"]]
    if p["counterparty_id"]:
        f["counterparty"] = [d.c.counterparty_id == p["counterparty_id"]]
    if p["year"]:
        f["year"] = [extract("year", d.c.doc_date) == p["year"]]
    if p["fiscal_year"]:
        f["fiscal_year"] = [d.c.fiscal_year == p["fiscal_year"]]
    dates = []
    if p["date_from"]:
        dates.append(d.c.doc_date >= p["date_from"])
    if p["date_to"]:
        dates.append(d.c.doc_date <= p["date_to"])
    if dates:
        f["date"] = dates
    amounts = []
    if p["amount_min"] is not None:
        amounts.append(d.c.amount >= p["amount_min"])
    if p["amount_max"] is not None:
        amounts.append(d.c.amount <= p["amount_max"])
    if amounts:
        f["amount"] = amounts
    tsq = None
    if p["q"]:
        tsq = func.websearch_to_tsquery("mona", norm(p["q"]))
        f["q"] = [d.c.fts.op("@@")(tsq)]

    def where(skip: str | None = None) -> list[Any]:
        return base + [x for k, v in f.items() if k != skip for x in v]

    sort = p["sort"] or ("relevance" if tsq is not None else "date_desc")
    if sort == "relevance" and tsq is None:
        sort = "date_desc"
    order = {
        "relevance": [func.ts_rank(d.c.fts, tsq).desc(), d.c.doc_date.desc().nulls_last()]
        if tsq is not None
        else [],
        "date_desc": [d.c.doc_date.desc().nulls_last()],
        "date_asc": [d.c.doc_date.asc().nulls_last()],
        "arrived_desc": [d.c.arrived_at.desc()],
        "amount_desc": [d.c.amount.desc().nulls_last()],
    }[sort] + [d.c.id]
    total = conn.execute(select(func.count()).select_from(d).where(*where())).scalar_one()
    ids = (
        conn.execute(
            select(d.c.id).where(*where()).order_by(*order).offset(p["offset"]).limit(p["limit"])
        )
        .scalars()
        .all()
    )
    snap = registry.load(conn)
    entities = conn.execute(
        select(e.c.id, e.c.display_name, func.count(d.c.id))
        .join(d, d.c.entity_id == e.c.id)
        .where(*where("entity"))
        .group_by(e.c.id, e.c.display_name, e.c.sort_order)
        .order_by(e.c.sort_order, e.c.display_name)
    ).all()
    year = extract("year", d.c.doc_date)
    years = conn.execute(
        select(year, func.count())
        .where(*where("year"), d.c.doc_date.is_not(None))
        .group_by(year)
        .order_by(year.desc())
    ).all()
    cats = conn.execute(
        select(c.c.id, c.c.labels, func.count(d.c.id))
        .join(d, d.c.category_id == c.c.id)
        .where(*where("category"))
        .group_by(c.c.id, c.c.labels, c.c.sort_order)
        .order_by(c.c.sort_order, c.c.id)
    ).all()
    cps = conn.execute(
        select(cp.c.id, cp.c.name, func.count(d.c.id))
        .join(d, d.c.counterparty_id == cp.c.id)
        .where(*where("counterparty"))
        .group_by(cp.c.id, cp.c.name)
        .order_by(func.count(d.c.id).desc(), cp.c.name)
        .limit(TOP_COUNTERPARTIES)
    ).all()
    statuses = conn.execute(
        select(d.c.status, func.count()).where(*where("status")).group_by(d.c.status)
    ).all()
    lo, hi = conn.execute(
        select(func.min(d.c.amount), func.max(d.c.amount)).where(*where("amount"))
    ).one()
    return {
        "items": views.summaries(conn, snap, list(ids)),
        "total": total,
        "offset": p["offset"],
        "limit": p["limit"],
        "facets": {
            "entities": [{"id": i, "name": n, "count": k} for i, n, k in entities],
            "years": [{"year": int(y), "count": k} for y, k in years],
            "categories": [
                {"id": i, "label": labels.get(lang, labels["en"]), "count": k}
                for i, labels, k in cats
            ],
            "counterparties": [{"id": i, "name": n, "count": k} for i, n, k in cps],
            "statuses": [{"status": s, "count": k} for s, k in sorted(statuses)],
            "amount": {
                "min": float(lo) if lo is not None else None,
                "max": float(hi) if hi is not None else None,
            },
        },
    }


@router.get(
    "/documents", operation_id="searchDocuments", responses=errors(400, 401, 423),
    response_model=DocumentPage,
)  # fmt: skip
async def search_documents(
    lang: Lang,
    q: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    entityId: str | None = None,  # noqa: N803
    categoryId: str | None = None,  # noqa: N803
    counterpartyId: str | None = None,  # noqa: N803
    year: Annotated[int | None, Query(ge=1900, le=2100)] = None,
    fiscalYear: Annotated[int | None, Query(ge=1900, le=2100)] = None,  # noqa: N803
    dateFrom: date | None = None,  # noqa: N803
    dateTo: date | None = None,  # noqa: N803
    amountMin: Annotated[float | None, Query(ge=0)] = None,  # noqa: N803
    amountMax: Annotated[float | None, Query(ge=0)] = None,  # noqa: N803
    status: Annotated[list[Status] | None, Query()] = None,
    sort: Sort | None = None,
    offset: Offset = 0,
    limit: PageLimit = 50,
) -> dict[str, Any]:
    body_id(entityId, "ent", "entityId")
    body_id(counterpartyId, "cpt", "counterpartyId")
    params = {
        "q": q, "entity_id": entityId, "category_id": categoryId,
        "counterparty_id": counterpartyId, "year": year, "fiscal_year": fiscalYear,
        "date_from": dateFrom, "date_to": dateTo, "amount_min": amountMin,
        "amount_max": amountMax, "status": status, "sort": sort, "offset": offset,
        "limit": limit,
    }  # fmt: skip

    def work() -> dict[str, Any]:
        with _conn() as conn:
            return _search(conn, lang, params)

    return await run(work)


# --- §4.2 detail ---


def _detail(document_id: str, lang: str) -> dict[str, Any]:
    with _conn() as conn:
        doc = views.doc_row(conn, document_id)
        if doc is None:
            raise ApiFailure(404, "not_found", "No document with that id.")
        return views.detail(conn, registry.load(conn), doc, lang)


@router.get(
    "/documents/{id}", operation_id="getDocument", response_model=DocumentDetail,
    responses=errors(401, 404, 423),
)  # fmt: skip
async def get_document(document_id: DocId, lang: Lang, request: Request) -> Response:
    return polled(request, DocumentDetail, await run(_detail, document_id, lang))


# --- §4.3 files ---


def _content_disposition(kind: str, name: str) -> str:
    return f"{kind}; filename*=UTF-8''{quote(name, safe='')}"


def _cache_file(ctx: Ctx, sha: str, suffix: str) -> Any:
    p = ctx.textcache / sha[:2] / f"{sha}.{suffix}"
    return p if p.is_file() else None


def _live_doc(document_id: str) -> Mapping[str, Any]:
    with _conn() as conn:
        doc = views.doc_row(conn, document_id)
    if doc is None:
        raise ApiFailure(404, "not_found", "No document with that id.")
    return doc


def _archive_file(ctx: Ctx, doc: Mapping[str, Any]) -> Any:
    """The document's current bytes, resolved now through the C7 §3 guard (read side)."""
    root = ctx.ops.roots.root(doc["location"])
    try:
        path = resolve_inside(root, doc["current_path"])
    except FileOpError:
        logger.warning("document %s: path refused by the guard", doc["id"])
        raise ApiFailure(404, "not_found", "No document with that id.") from None
    if not path.is_file():
        raise ApiFailure(404, "not_found", "No document with that id.")
    return path


@router.get(
    "/documents/{id}/pdf", operation_id="getDocumentPdf", response_class=FileResponse,
    responses={200: {"content": {"application/pdf": {}}}, **errors(401, 404, 423)},
)  # fmt: skip
async def document_pdf(document_id: DocId, ctx: CtxDep) -> FileResponse:
    doc = await run(_live_doc, document_id)
    ocr = _cache_file(ctx, doc["sha256"], "ocr.pdf")
    if ocr is not None:
        path, etag = ocr, f'"{doc["sha256"]}.ocr"'
    elif doc["mime_type"] == "application/pdf":
        path, etag = _archive_file(ctx, doc), f'"{doc["sha256"]}"'
    else:
        raise ApiFailure(404, "not_ready", "The viewer copy isn't ready yet.")
    stem = doc["current_path"].rpartition("/")[2].rpartition(".")[0] or doc["id"]
    return FileResponse(
        path,
        media_type="application/pdf",
        headers={
            **FILE_HEADERS,
            "Content-Disposition": _content_disposition("inline", f"{stem}.pdf"),
            "ETag": etag,
            "Accept-Ranges": "bytes",
            "Content-Security-Policy": "sandbox",
        },
    )


@router.get(
    "/documents/{id}/original", operation_id="getDocumentOriginal", response_class=FileResponse,
    responses={200: {"content": {"application/octet-stream": {}}}, **errors(401, 404, 423)},
)  # fmt: skip
async def document_original(document_id: DocId, ctx: CtxDep) -> FileResponse:
    doc = await run(_live_doc, document_id)
    path = _archive_file(ctx, doc)
    name = doc["current_path"].rpartition("/")[2]
    return FileResponse(
        path,
        media_type=doc["mime_type"],
        headers={
            **FILE_HEADERS,
            "Content-Disposition": _content_disposition("attachment", name),
            "Content-Security-Policy": "sandbox",
        },
    )


@router.get(
    "/documents/{id}/thumbnail", operation_id="getDocumentThumbnail", response_class=FileResponse,
    responses={200: {"content": {"image/png": {}}}, **errors(401, 404, 423)},
)  # fmt: skip
async def document_thumbnail(document_id: DocId, ctx: CtxDep) -> FileResponse:
    doc = await run(_live_doc, document_id)
    thumb = _cache_file(ctx, doc["sha256"], "p1.png")
    if thumb is None:
        raise ApiFailure(404, "not_ready", "The thumbnail isn't ready yet.")
    return FileResponse(
        thumb,
        media_type="image/png",
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=86400"},
    )


# --- §4.5 folders ---


def _folders(path: list[str], entity_id: str | None) -> dict[str, Any]:
    d = T["documents"]
    clauses = [d.c.deleted_at.is_(None), d.c.location == "archive"]
    if entity_id:
        clauses.append(d.c.entity_id == entity_id)
    with _conn() as conn:
        rows = conn.execute(select(d.c.id, d.c.current_path).where(*clauses)).all()
        counts: dict[str, int] = {}
        deeper: set[str] = set()
        here: list[tuple[str, str]] = []
        n = len(path)
        for doc_id, current in rows:
            parts = current.split("/")
            folders, name = parts[:-1], parts[-1]
            if folders[:n] != path:
                continue
            if len(folders) == n:
                here.append((name, doc_id))
                continue
            child = folders[n]
            counts[child] = counts.get(child, 0) + 1
            if len(folders) > n + 1:
                deeper.add(child)
        here.sort(key=lambda x: (norm(x[0]), x[0]))
        snap = registry.load(conn)
        docs = views.summaries(conn, snap, [i for _, i in here])
    return {
        "path": path,
        "folders": [
            {
                "name": name,
                "path": [*path, name],
                "document_count": counts[name],
                "has_children": name in deeper,
            }
            for name in sorted(counts, key=lambda x: (norm(x), x))
        ],  # fmt: skip
        "documents": docs,
    }


@router.get(
    "/folders", operation_id="listFolders", response_model=FolderListing,
    responses=errors(400, 401, 423),
)  # fmt: skip
async def folders(
    path: Annotated[str, Query(max_length=2000)] = "",
    entityId: str | None = None,  # noqa: N803
) -> dict[str, Any]:
    body_id(entityId, "ent", "entityId")
    segments = [s for s in path.split("/") if s] if path else []
    return await run(_folders, segments, entityId)


# --- §6.1 review ---


def _review(reason: str | None, entity_id: str | None, offset: int, limit: int) -> dict:
    d = T["documents"]
    clauses = [d.c.deleted_at.is_(None), d.c.status.in_(("review", "unreadable"))]
    if reason:
        clauses.append(any_(d.c.reasons) == reason)
    if entity_id:
        clauses.append(d.c.entity_id == entity_id)
    with _conn() as conn:
        total = conn.execute(select(func.count()).select_from(d).where(*clauses)).scalar_one()
        ids = (
            conn.execute(
                select(d.c.id)
                .where(*clauses)
                .order_by(d.c.arrived_at, d.c.id)
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .all()
        )
        items = views.summaries(conn, registry.load(conn), list(ids))
    return {"items": items, "total": total, "offset": offset, "limit": limit}


@router.get(
    "/review", operation_id="listReview", response_model=Page[DocumentSummary],
    responses=errors(400, 401, 423),
)  # fmt: skip
async def review(
    reason: Literal["low", "entity", "conflict", "unreadable"] | None = None,
    entityId: str | None = None,  # noqa: N803
    offset: Offset = 0,
    limit: PageLimit = 50,
) -> dict[str, Any]:
    body_id(entityId, "ent", "entityId")
    return await run(_review, reason, entityId, offset, limit)


# --- §6.2 document actions ---


def _result(
    ctx: Ctx, document_id: str, lang: str, *, outcome: str, journal_ids: list[int],
    group_id: str | None, undo: dict[str, Any] | None, deleted: bool = False,
) -> dict[str, Any]:  # fmt: skip
    document = None
    if not deleted:
        with _conn() as conn:
            doc = views.doc_row(conn, document_id)
            document = views.detail(conn, registry.load(conn), doc, lang) if doc else None
    return {
        "document": document,
        "outcome": outcome,
        "journal_ids": journal_ids,
        "group_id": group_id,
        "undo": undo,
    }


def _move(ctx: Ctx, change: Change) -> Any:
    try:
        return ctx.ops.move(change)
    except FileOpError as err:
        from mona.api.errors import from_service

        raise from_service(err) from None


def _confirm(ctx: Ctx, document_id: str, lang: str) -> dict[str, Any]:
    c = T["classifications"]
    with _conn() as conn:
        doc = views.doc_row(conn, document_id)
        if doc is None:
            raise ApiFailure(404, "not_found", "No document with that id.")
        if doc["status"] == "filed":
            return _result(ctx, document_id, lang, outcome="unchanged", journal_ids=[],
                           group_id=None, undo=None)  # fmt: skip
        cls = None
        if doc["classification_id"]:
            cls = (
                conn.execute(select(c).where(c.c.id == doc["classification_id"])).mappings().first()
            )
    if doc["status"] == "processing":
        raise ApiFailure(409, "conflict", "The document is still being read.",
                         details={"reason": "processing"})  # fmt: skip
    if (
        cls is None
        or cls["entity_id"] is None
        or not cls["proposed_path"]
        or not cls["proposed_file_name"]
    ):
        raise ApiFailure(422, "not_renderable", "The suggestion has no entity or no path.")
    r = _move(
        ctx,
        Change(
            document_id=document_id, action="file", location="archive",
            path=f"{cls['proposed_path']}/{cls['proposed_file_name']}", actor="user", via="ui",
            expected=(doc["location"], doc["current_path"]), status="filed", reasons=(),
            classification_id=cls["id"], rule_id=cls["rule_id"], resolution="confirmed",
        ),
    )  # fmt: skip
    moved = r.outcome == "moved"
    return _result(
        ctx, document_id, lang, outcome=r.outcome, journal_ids=[r.entry_id] if moved else [],
        group_id=None, undo={"journal_id": r.entry_id} if moved else None,
    )  # fmt: skip


@router.post(
    "/documents/{id}/confirm", operation_id="confirmDocument", response_model=FileOpResult,
    responses=errors(401, 403, 404, 409, 415, 422, 423),
)  # fmt: skip
async def confirm_document(document_id: DocId, ctx: CtxDep, lang: Lang) -> dict[str, Any]:
    return await run(_confirm, ctx, document_id, lang)


NULLABLE = {"sub_unit_id": "sub_unit", "subcategory_key": "subcategory", "due_date": "due_date",
            "amount": "amount"}  # fmt: skip


def _correct(ctx: Ctx, document_id: str, body: CorrectionRequest, lang: str) -> dict[str, Any]:
    given = {k: getattr(body, k) for k in body.model_fields_set}
    if not given:
        raise ApiFailure(400, "invalid_request", "Give at least one correction.")
    clear = {NULLABLE[k] for k, v in given.items() if k in NULLABLE and v is None}
    body_id(body.entity_id, "ent", "entityId")
    body_id(body.sub_unit_id, "sub", "subUnitId")
    kw: dict[str, Any] = {}
    with _conn() as conn:
        snap = registry.load(conn)
        if views.doc_row(conn, document_id) is None:
            raise ApiFailure(404, "not_found", "No document with that id.")
        if body.entity_id is not None:
            kw["entity"] = _key(snap.entity_keys, body.entity_id, "entityId")
        if body.sub_unit_id is not None:
            kw["sub_unit"] = _key(snap.sub_unit_keys, body.sub_unit_id, "subUnitId")[1]
        if body.category_id is not None:
            if body.category_id not in snap.categories:
                raise ApiFailure(400, "invalid_request", "Unknown category.", field="categoryId")
            kw["category"] = body.category_id
        if body.subcategory_key is not None:
            kw["subcategory"] = body.subcategory_key
        if isinstance(body.counterparty, CounterpartyById):
            body_id(body.counterparty.id, "cpt", "counterparty.id")
            key = _key(snap.counterparty_keys, body.counterparty.id, "counterparty.id")
            kw["counterparty"] = snap.counterparties[key]["name"]
        elif body.counterparty is not None:
            kw["counterparty"] = body.counterparty.name
    for name in ("doc_date", "period_end", "due_date"):
        if given.get(name) is not None:
            kw[name] = getattr(body, name)
    if body.amount is not None:
        kw["amount"], kw["currency"] = body.amount.value, body.amount.currency
    result = correct_document(
        ctx, document_id, actor="user", via="ui", lang=lang, clear=clear, **kw
    )
    moved = result.outcome == "moved"
    if result.group_id and moved:
        _close_scope(document_id, "one", None)
    return _result(
        ctx, document_id, lang, outcome=result.outcome, journal_ids=result.journal_ids,
        group_id=result.group_id if moved else None,
        undo={"group_id": result.group_id} if moved and result.group_id else None,
    )  # fmt: skip


def _key(mapping: dict[str, Any], value: str, field: str) -> Any:
    if value not in mapping:
        raise ApiFailure(400, "invalid_request", "Unknown id.", field=field)
    return mapping[value]


def _close_scope(document_id: str, scope: str, rule_id: str | None) -> None:
    """C2 §6.2: the closed review item records the `CorrectionScopePrompt` answer."""
    r = T["review_items"]
    with get_sync_engine().begin() as conn:
        item = conn.execute(
            select(r.c.id)
            .where(r.c.document_id == document_id, r.c.resolution == "corrected")
            .order_by(r.c.resolved_at.desc().nulls_last(), r.c.id.desc())
            .limit(1)
        ).scalar()
        if item is not None:
            values: dict[str, Any] = {"scope": scope}
            if rule_id is not None:
                values["rule_id"] = rule_id
            conn.execute(update(r).where(r.c.id == item).values(**values))


@router.post(
    "/documents/{id}/correct", operation_id="correctDocument", response_model=FileOpResult,
    responses=errors(400, 401, 403, 404, 409, 415, 422, 423),
)  # fmt: skip
async def correct(
    document_id: DocId, body: CorrectionRequest, ctx: CtxDep, lang: Lang
) -> dict[str, Any]:
    return await run(_correct, ctx, document_id, body, lang)


def _like_this(ctx: Ctx, document_id: str, lang: str) -> dict[str, Any]:
    c = T["classifications"]
    now = clock.now()
    with get_sync_engine().begin() as conn:
        doc = views.doc_row(conn, document_id)
        if doc is None:
            raise ApiFailure(404, "not_found", "No document with that id.")
        cls = (
            conn.execute(
                select(c)
                .where(c.c.document_id == document_id, c.c.method == "user")
                .order_by(c.c.created_at.desc(), c.c.id.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        if cls is None:
            raise ApiFailure(404, "not_found", "The document has no correction.")
        if cls["counterparty_id"] is None:
            raise ApiFailure(422, "invalid_value", "The document has no counterparty.",
                             field="counterparty")  # fmt: skip
        snap = registry.load(conn)
        unit = snap.sub_unit_keys.get(cls["sub_unit_id"], (None, None))[1]
        row, _ = draft_from_correction(
            conn, snap, doc, entity=snap.entity_keys.get(cls["entity_id"]), unit=unit,
            category=cls["category_id"], subcategory=cls["subcategory_key"],
            counterparty_id=cls["counterparty_id"], actor="user", via="ui", at=now,
            group_id=None, textcache=ctx.textcache,
        )  # fmt: skip
    with _conn() as conn:
        store.write_export(conn, ctx.config_dir, now=now)
    _close_scope_any(document_id, row["id"])
    preview = preview_rule(ctx, row["id"], lang=lang)
    return LikeThisResult(rule=preview.rule, preview=preview).model_dump(mode="json")


def _close_scope_any(document_id: str, rule_id: str) -> None:
    r = T["review_items"]
    with get_sync_engine().begin() as conn:
        item = conn.execute(
            select(r.c.id)
            .where(r.c.document_id == document_id, r.c.status == "resolved")
            .order_by(r.c.resolved_at.desc().nulls_last(), r.c.id.desc())
            .limit(1)
        ).scalar()
        if item is not None:
            conn.execute(update(r).where(r.c.id == item).values(scope="all", rule_id=rule_id))


@router.post(
    "/documents/{id}/like-this", operation_id="draftRuleLikeThis",
    response_model=LikeThisResult, responses=errors(400, 401, 403, 404, 415, 422, 423),
)  # fmt: skip
async def like_this(
    document_id: DocId, ctx: CtxDep, lang: Lang, body: ConversationRef | None = None
) -> dict[str, Any]:
    if body is not None:
        body_id(body.conversation_id, "cnv", "conversationId")
    return await run(_like_this, ctx, document_id, lang)


def _unfile(ctx: Ctx, document_id: str, lang: str) -> dict[str, Any]:
    c = T["classifications"]
    with _conn() as conn:
        doc = views.doc_row(conn, document_id)
        if doc is None:
            raise ApiFailure(404, "not_found", "No document with that id.")
        reasons: list[str] = []
        if doc["classification_id"]:
            reasons = list(
                conn.execute(select(c.c.reasons).where(c.c.id == doc["classification_id"])).scalar()
                or []
            )
    if doc["location"] != "archive":
        return _result(ctx, document_id, lang, outcome="unchanged", journal_ids=[],
                       group_id=None, undo=None)  # fmt: skip
    r = _move(
        ctx,
        Change(
            document_id=document_id, action="unfile", location="inbox",
            path=inbox_name(document_id, doc["mime_type"]), actor="user", via="ui",
            expected=(doc["location"], doc["current_path"]), status="review",
            reasons=tuple(reasons or ["low"]),
        ),
    )  # fmt: skip
    moved = r.outcome == "moved"
    return _result(
        ctx, document_id, lang, outcome=r.outcome, journal_ids=[r.entry_id] if moved else [],
        group_id=None, undo={"journal_id": r.entry_id} if moved else None,
    )  # fmt: skip


@router.post(
    "/documents/{id}/unfile", operation_id="unfileDocument", response_model=FileOpResult,
    responses=errors(401, 403, 404, 409, 415, 423),
)  # fmt: skip
async def unfile(document_id: DocId, ctx: CtxDep, lang: Lang) -> dict[str, Any]:
    return await run(_unfile, ctx, document_id, lang)


def _delete(ctx: Ctx, document_id: str, body: DeleteRequest, lang: str) -> dict[str, Any]:
    if body.confirm is not True:
        raise ApiFailure(400, "invalid_request", "Deleting needs confirm: true.", field="confirm")
    with _conn() as conn:
        doc = views.doc_row(conn, document_id)
    if doc is None:
        raise ApiFailure(404, "not_found", "No document with that id.")
    if doc["current_path"].rpartition("/")[2] != body.file_name:
        raise ApiFailure(
            422, "invalid_value", "The typed name isn't the document's current file name.",
            field="fileName", details={"field": "fileName"},
        )  # fmt: skip
    try:
        r = ctx.ops.delete(
            document_id, actor="user", via="ui", expected=(doc["location"], doc["current_path"])
        )
    except FileOpError as err:
        from mona.api.errors import from_service

        raise from_service(err) from None
    return _result(
        ctx, document_id, lang, outcome=r.outcome, journal_ids=[r.entry_id] if r.entry_id else [],
        group_id=None, undo={"journal_id": r.entry_id} if r.entry_id else None, deleted=True,
    )  # fmt: skip


@router.post(
    "/documents/{id}/delete", operation_id="deleteDocument", response_model=FileOpResult,
    responses=errors(400, 401, 403, 404, 409, 415, 422, 423),
)  # fmt: skip
async def delete_document(
    document_id: DocId, body: DeleteRequest, ctx: CtxDep, lang: Lang
) -> dict[str, Any]:
    return await run(_delete, ctx, document_id, body, lang)

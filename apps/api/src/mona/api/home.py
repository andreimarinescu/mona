"""C2 §3 shell counters and Home."""

import time
from datetime import datetime, timedelta
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import Connection, func, select, text

from mona import brief, clock
from mona.api import journal, views
from mona.api.deps import Engine, body_id, polled, run
from mona.api.errors import errors
from mona.api.models import HomeView, ShellState
from mona.db import get_sync_engine
from mona.db.models import Deadline
from mona.services import registry
from mona.services.registry import T
from mona.settings import get_settings
from mona.visibility import scope_for

router = APIRouter(prefix="/api", tags=["home"])

HERMES_TIMEOUT_S = 2.0
HERMES_CACHE_S = 15.0
HOME_ITEMS = 3
INGESTION_DAYS = 14

_hermes: dict[str, Any] = {"at": float("-inf"), "health": None}


async def hermes_health() -> dict[str, Any] | None:
    """Hermes `GET /health` within 2 s, cached 15 s; None when it didn't answer."""
    now = time.monotonic()
    if now - _hermes["at"] < HERMES_CACHE_S:
        return _hermes["health"]
    health = None
    try:
        async with httpx.AsyncClient(timeout=HERMES_TIMEOUT_S) as client:
            res = await client.get(f"{get_settings().hermes_url}/health")
        if res.status_code == 200:
            body = res.json()
            health = body if isinstance(body, dict) else {}
    except (httpx.HTTPError, ValueError):
        health = None
    _hermes.update(at=now, health=health)
    return health


def queue_counts(conn: Connection) -> dict[str, dict[str, int]]:
    """Procrastinate jobs per queue and status (todo, doing)."""
    out = {q: {"todo": 0, "doing": 0} for q in ("llm", "cpu")}
    rows = conn.execute(
        text(
            "SELECT queue_name, status::text, count(*) FROM procrastinate_jobs"
            " WHERE status IN ('todo', 'doing') AND queue_name IN ('llm', 'cpu')"
            " GROUP BY queue_name, status"
        )
    ).all()
    for queue, status, n in rows:
        out[queue][status] = n
    return out


def _shell_counts() -> dict[str, Any]:
    d, r = T["documents"], T["review_items"]
    with get_sync_engine().connect() as conn:
        review = conn.execute(
            select(func.count())
            .select_from(r)
            .join(d, d.c.id == r.c.document_id)
            .where(r.c.status == "open", d.c.deleted_at.is_(None))
        ).scalar_one()
        processing = conn.execute(
            select(func.count()).where(d.c.status == "processing", d.c.deleted_at.is_(None))
        ).scalar_one()
        queues = queue_counts(conn)
    return {
        "review_count": review,
        "processing_count": processing,
        "queue": {q: c["todo"] + c["doing"] for q, c in queues.items()},
    }


@router.get(
    "/shell", operation_id="getShell", response_model=ShellState, responses=errors(401, 423)
)
async def shell(request: Request) -> Response:
    body = await run(_shell_counts)
    body["mona"] = "online" if await hermes_health() is not None else "offline"
    return polled(request, ShellState, body)


def start_of_paris_day(at: datetime) -> datetime:
    day = clock.paris_today(at)
    return datetime(day.year, day.month, day.day, tzinfo=clock.PARIS)


def _home_rest(
    facts: dict[str, Any], soon: list[str], due: tuple[int, list[str]], since: datetime,
    entity_id: str | None,
) -> dict[str, Any]:  # fmt: skip
    d, f, dl, b = T["documents"], T["file_ops"], T["deadlines"], T["batches"]
    now = clock.now()
    with get_sync_engine().connect() as conn:
        snap = registry.load(conn)
        facts["due_soon"] = views.deadlines(conn, dl.c.id.in_(soon))
        entries = select(func.count()).select_from(f).where(f.c.fs_state == "done", f.c.at >= since)
        if entity_id:
            entries = entries.join(d, d.c.id == f.c.document_id).where(d.c.entity_id == entity_id)
        review = [d.c.deleted_at.is_(None), d.c.status.in_(("review", "unreadable"))]
        if entity_id:
            review.append(d.c.entity_id == entity_id)
        review_total = conn.execute(select(func.count()).where(*review)).scalar_one()
        review_ids = conn.execute(
            select(d.c.id).where(*review).order_by(d.c.arrived_at, d.c.id).limit(HOME_ITEMS)
        ).scalars()
        first_day = clock.paris_today(now) - timedelta(days=INGESTION_DAYS - 1)
        day = func.date(func.timezone("Europe/Paris", d.c.arrived_at))
        arrivals = [day >= first_day, d.c.deleted_at.is_(None)]
        if entity_id:
            arrivals.append(d.c.entity_id == entity_id)
        per_day = dict(conn.execute(select(day, func.count()).where(*arrivals).group_by(day)).all())
        last_batch = conn.execute(
            select(b.c.id).order_by(b.c.started_at.desc(), b.c.id.desc()).limit(1)
        ).scalar()
        return {
            "facts": facts,
            "journal_entry_count": conn.execute(entries).scalar_one(),
            "review": {
                "total": review_total,
                "items": views.summaries(conn, snap, list(review_ids)),
            },
            "due": {"total": due[0], "items": views.deadlines(conn, dl.c.id.in_(due[1]))},
            "ingestion": {
                "days": [
                    {
                        "date": first_day + timedelta(days=i),
                        "count": per_day.get(first_day + timedelta(days=i), 0),
                    }
                    for i in range(INGESTION_DAYS)
                ],  # fmt: skip
                "last_batch": views.batch_summary(conn, last_batch) if last_batch else None,
            },
        }


@router.get(
    "/home", operation_id="getHome", response_model=HomeView, responses=errors(400, 401, 423)
)
async def home(
    engine: Engine,
    since: datetime | None = None,
    entityId: Annotated[str | None, Query()] = None,  # noqa: N803
) -> dict[str, Any]:
    body_id(entityId, "ent", "entityId")
    now = clock.now()
    since = since or start_of_paris_day(now)
    async with engine.connect() as conn:
        scope = await scope_for(conn, "web")
        f = await brief.facts(
            scope, since=since, now=now, today=clock.paris_today(now), entity_id=entityId
        )
        open_due = brief.deadline_query(
            scope, *([Deadline.entity_id == entityId] if entityId else [])
        ).subquery()
        due_total = (await conn.execute(select(func.count()).select_from(open_due))).scalar_one()
        due_ids = (
            (
                await conn.execute(
                    select(open_due.c.id)
                    .order_by(open_due.c.due_date, open_due.c.id)
                    .limit(HOME_ITEMS)
                )
            )
            .scalars()
            .all()
        )
    facts = {
        "generated_at": now,
        "since": since,
        "filed": {
            "count": sum(r[3] for r in f.filed),
            "by_entity": [{"entity_id": r[0], "name": r[2], "count": r[3]} for r in f.filed],
        },
        "needs_review": {"count": len(f.review_reasons), "by_reason": f.by_reason},
        "reminders_today": [
            {"reminder_id": r.id, "label": r.label, "note": r.note} for r in f.reminders
        ],
        "learned": [
            {"rule_id": r.id, "name": r.name, "created_at": r.created_at, "fired_since": r.fired}
            for r in f.learned
        ],
        "pending_interview": (
            {"interview_id": f.pending.id, "open_questions": f.pending.n} if f.pending else None
        ),
    }
    out = await run(
        _home_rest, facts, [r.id for r in f.due], (due_total, list(due_ids)), since, entityId
    )
    activity = await run(
        journal.activity_page,
        {"actor": None, "entity_id": entityId, "kind": None, "q": None, "cursor": None,
         "limit": HOME_ITEMS},
    )  # fmt: skip
    out["activity"] = {k: activity[k] for k in ("items", "documents", "rules")}
    return out

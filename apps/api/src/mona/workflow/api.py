"""C2 §10 (deadlines, reminders) and §12 (drafts, exports)."""

from datetime import date, timedelta
from functools import partial
from typing import Annotated, Any

import anyio
from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import FileResponse
from pydantic import Field
from sqlalchemy import func, select

from mona import brief, clock
from mona.db import get_engine
from mona.db.models import Deadline, Export, Profile
from mona.dto import load
from mona.dto import models as dto
from mona.dto.base import Dto
from mona.ids import is_id
from mona.services import ServiceError
from mona.visibility import scope_for
from mona.workflow import deadlines, drafts, exports
from mona.workflow.common import RestError, errors, from_service, get_ctx, not_found
from mona.workflow.http import Page, etagged

router = APIRouter(prefix="/api", tags=["workflow"])
ConversationId = Annotated[str | None, Field(pattern=r"^cnv_[0-9a-hjkmnp-tv-z]{26}$")]


def _id(value: str, prefix: str, what: str) -> None:
    if not is_id(value, prefix):
        raise not_found(what)


async def _run(fn: Any, *args: Any, **kwargs: Any) -> Any:
    try:
        return await anyio.to_thread.run_sync(partial(fn, *args, **kwargs))
    except ServiceError as err:
        if err.hint == "not_ready":
            raise RestError(404, "not_ready", err.message) from None
        raise from_service(err) from None


# --- §10 deadlines and reminders ---


class DeadlinePatch(Dto):
    status: dto.DeadlineStatus


class ReminderCreate(Dto):
    deadline_id: Annotated[str | None, Field(pattern=r"^ddl_[0-9a-hjkmnp-tv-z]{26}$")] = None
    document_id: Annotated[str | None, Field(pattern=r"^doc_[0-9a-hjkmnp-tv-z]{26}$")] = None
    remind_on: date
    note: str | None = Field(default=None, max_length=200)
    conversation_id: ConversationId = None


class ReminderResult(Dto):
    reminder_id: str
    remind_on: date
    created: bool
    deadline: dto.Deadline | None


@router.get(
    "/deadlines",
    operation_id="listDeadlines",
    response_model=Page[dto.Deadline],
    responses=errors(400, 401, 423),
)
async def list_deadlines(
    within_days: Annotated[int, Query(alias="withinDays", ge=0, le=366)] = 30,
    include_overdue: Annotated[bool, Query(alias="includeOverdue")] = True,
    status: dto.DeadlineStatus = "open",
    entity_id: Annotated[str | None, Query(alias="entityId")] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> Page[dto.Deadline]:
    if entity_id is not None and not is_id(entity_id, "ent"):
        raise RestError(400, "invalid_request", "Not an entity id.", field="entityId")
    today = clock.paris_today()
    clauses: list[Any] = [Deadline.due_date <= today + timedelta(days=within_days)]
    if not include_overdue:
        clauses.append(Deadline.due_date >= today)
    if entity_id is not None:
        clauses.append(Deadline.entity_id == entity_id)
    async with get_engine().connect() as conn:
        q = brief.deadline_query(await scope_for(conn, "web"), *clauses, statuses=(status,))
        total = (await conn.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
        ids = (
            (
                await conn.execute(
                    q.with_only_columns(Deadline.id)
                    .order_by(Deadline.due_date, Deadline.id)
                    .offset(offset)
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        found = await load.deadlines(conn, list(ids))
    return Page(
        items=[found[i] for i in ids if i in found], total=total, offset=offset, limit=limit
    )


async def _deadline(deadline_id: str) -> dto.Deadline:
    async with get_engine().connect() as conn:
        found = (await load.deadlines(conn, [deadline_id])).get(deadline_id)
    if found is None:
        raise not_found("deadline")
    return found


@router.patch(
    "/deadlines/{deadline_id}",
    operation_id="updateDeadline",
    response_model=dto.Deadline,
    responses=errors(400, 401, 403, 404, 415, 423),
)
async def update_deadline(deadline_id: str, body: DeadlinePatch) -> dto.Deadline:
    _id(deadline_id, "ddl", "deadline")
    await _run(deadlines.set_status, get_ctx(), deadline_id, body.status)
    return await _deadline(deadline_id)


@router.post(
    "/reminders",
    operation_id="createReminder",
    response_model=ReminderResult,
    status_code=201,
    responses=errors(400, 401, 403, 404, 415, 422, 423),
)
async def create_reminder(body: ReminderCreate, response: Response) -> ReminderResult:
    if (body.deadline_id is None) == (body.document_id is None):
        raise RestError(
            400, "invalid_request", "Give deadlineId or documentId.", field="deadlineId"
        )
    try:
        out = await anyio.to_thread.run_sync(
            partial(
                deadlines.add_reminder,
                get_ctx(),
                deadline_id=body.deadline_id,
                document_id=body.document_id,
                remind_on=body.remind_on,
                note=body.note,
                actor="user",
                via="ui",
                conversation_id=body.conversation_id,
            )
        )
    except ServiceError as err:
        if err.field == "remind_on":
            raise RestError(422, "invalid_value", err.message, field="remindOn") from None
        raise from_service(err) from None
    if not out.created:
        response.status_code = 200
    deadline = await _deadline(out.deadline_id) if out.deadline_id else None
    return ReminderResult(
        reminder_id=out.reminder_id, remind_on=out.remind_on, created=out.created, deadline=deadline
    )


@router.delete(
    "/reminders/{reminder_id}",
    operation_id="cancelReminder",
    status_code=204,
    responses=errors(401, 403, 404, 415, 423),
)
async def cancel_reminder(reminder_id: str) -> Response:
    _id(reminder_id, "rem", "reminder")
    await _run(deadlines.cancel_reminder, get_ctx(), reminder_id)
    return Response(status_code=204)


# --- §12 drafts ---


@router.get(
    "/drafts/{draft_id}",
    operation_id="getDraft",
    response_model=dto.Draft,
    responses=errors(401, 404, 423),
)
async def get_draft(draft_id: str, request: Request) -> Response:
    _id(draft_id, "drf", "draft")
    async with get_engine().connect() as conn:
        found = await load.draft(conn, draft_id)
    if found is None:
        raise not_found("draft")
    return etagged(request, found)


DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@router.get(
    "/drafts/{draft_id}/docx",
    operation_id="downloadDraft",
    response_class=Response,
    responses={200: {"content": {DOCX: {}}}, **errors(401, 404, 423)},
)
async def download_draft(
    draft_id: str, conversation_id: Annotated[str | None, Query(alias="conversationId")] = None
) -> Response:
    _id(draft_id, "drf", "draft")
    data, name = await _run(drafts.download, get_ctx(), draft_id, conversation_id=conversation_id)
    return Response(
        data, media_type=DOCX, headers={"content-disposition": f'attachment; filename="{name}"'}
    )


# --- §12 exports ---


class ExportCreate(Dto):
    entity_id: Annotated[str, Field(pattern=r"^ent_[0-9a-hjkmnp-tv-z]{26}$")]
    fiscal_year: int = Field(ge=2000, le=2100)


class ExportCategory(Dto):
    id: str
    label: str
    count: int


class ExportPreview(Dto):
    entity_id: str
    fiscal_year: int
    document_count: int
    in_review: int
    categories: list[ExportCategory]
    fiscal_years: list[int]


async def _export(export_id: str) -> dto.ExportPack:
    async with get_engine().connect() as conn:
        found = await load.export(conn, export_id)
    if found is None:
        raise not_found("export")
    return found


@router.get(
    "/exports",
    operation_id="listExports",
    response_model=Page[dto.ExportPack],
    responses=errors(400, 401, 423),
)
async def list_exports(
    entity_id: Annotated[str | None, Query(alias="entityId")] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> Page[dto.ExportPack]:
    clauses = [Export.entity_id == entity_id] if entity_id else []
    async with get_engine().connect() as conn:
        total = (
            await conn.execute(select(func.count()).select_from(Export).where(*clauses))
        ).scalar_one()
        ids = (
            (
                await conn.execute(
                    select(Export.id)
                    .where(*clauses)
                    .order_by(Export.created_at.desc(), Export.id.desc())
                    .offset(offset)
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        items = [await load.export(conn, i) for i in ids]
    return Page(items=[i for i in items if i], total=total, offset=offset, limit=limit)


@router.get(
    "/exports/preview",
    operation_id="previewExport",
    response_model=ExportPreview,
    responses=errors(400, 401, 403, 404, 423),
)
async def preview_export(
    entity_id: Annotated[str, Query(alias="entityId")],
    fiscal_year: Annotated[int, Query(alias="fiscalYear", ge=2000, le=2100)],
) -> ExportPreview:
    if not is_id(entity_id, "ent"):
        raise RestError(400, "invalid_request", "Not an entity id.", field="entityId")
    async with get_engine().connect() as conn:
        lang = (await conn.execute(select(Profile.locale))).scalar() or "en"

    def run() -> dict:
        with get_ctx().engine.connect() as conn:
            return exports.preview(conn, entity_id, fiscal_year, lang)

    return ExportPreview.model_validate(await _run(run))


@router.post(
    "/exports",
    operation_id="createExport",
    response_model=dto.ExportPack,
    status_code=201,
    responses=errors(400, 401, 403, 404, 415, 423),
)
async def create_export(body: ExportCreate, response: Response) -> dto.ExportPack:
    started = await _run(exports.start_export, get_ctx(), body.entity_id, body.fiscal_year)
    if not started.created:
        response.status_code = 200
    return await _export(started.export_id)


@router.get(
    "/exports/{export_id}",
    operation_id="getExport",
    response_model=dto.ExportPack,
    responses=errors(401, 404, 423),
)
async def get_export(export_id: str, request: Request) -> Response:
    _id(export_id, "exp", "export")
    return etagged(request, await _export(export_id))


async def _file(export_id: str, kind: str, media: str) -> FileResponse:
    _id(export_id, "exp", "export")
    path, name = await _run(exports.file_path, get_ctx(), export_id, kind)
    return FileResponse(path, media_type=media, filename=name)


@router.get(
    "/exports/{export_id}/zip",
    operation_id="downloadExportZip",
    response_class=FileResponse,
    responses=errors(401, 404, 423),
)
async def export_zip(export_id: str) -> FileResponse:
    return await _file(export_id, "zip", "application/zip")


@router.get(
    "/exports/{export_id}/csv",
    operation_id="downloadExportCsv",
    response_class=FileResponse,
    responses=errors(401, 404, 423),
)
async def export_csv(export_id: str) -> FileResponse:
    return await _file(export_id, "csv", "text/csv; charset=utf-8")

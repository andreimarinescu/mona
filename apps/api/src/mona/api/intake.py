"""C2 §5 intake: the upload (limits checked while the body streams, then one batch) and batches."""

import shutil
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import IO, Any

import anyio.to_thread
from fastapi import APIRouter, Request, Response
from python_multipart import MultipartParser
from python_multipart.exceptions import MultipartParseError
from python_multipart.multipart import parse_options_header
from sqlalchemy import Connection, func, literal_column, select, update

from mona import clock
from mona.api import views
from mona.api.deps import Offset, Page, PageLimit, path_id, polled, run
from mona.api.errors import ApiFailure, errors
from mona.api.models import BatchDetail, BatchPatch, BatchSummary, IntakeResult
from mona.db import get_sync_engine
from mona.pipeline.hooks import interview_hooks
from mona.pipeline.intake import Intake, Upload, ingest_files
from mona.services import Ctx, make_context, registry
from mona.services.registry import T
from mona.settings import get_settings

router = APIRouter(prefix="/api", tags=["intake"])

BatchId = path_id("bat", "id")
MIB = 1024 * 1024
MAX_FILES = 50
MAX_FILE_BYTES = 25 * MIB
MAX_FIELD_BYTES = 1024
MAX_TITLE = 120
FIELDS = ("visitor", "title")
# Rows of one upload share created_at and may share the ULID's millisecond; ctid breaks the tie.
UPLOAD_ORDER = (
    T["intake_items"].c.created_at,
    func.left(T["intake_items"].c.id, 14),
    literal_column("intake_items.ctid"),
)

UPLOAD_BODY = {
    "required": True,
    "content": {
        "multipart/form-data": {
            "schema": {
                "type": "object",
                "required": ["file"],
                "properties": {
                    "file": {"type": "array", "items": {"type": "string", "format": "binary"}},
                    "visitor": {"type": "string", "enum": ["true", "false"]},
                    "title": {"type": "string", "maxLength": MAX_TITLE},
                },
            }
        }
    },
}


@lru_cache
def get_intake_ctx() -> Ctx:
    """The pipeline context with the C6 batch hooks, as the workers have it."""
    data_dir = get_settings().mona_data_dir
    return make_context(get_sync_engine(), data_dir, clock=lambda: clock.now(), **interview_hooks())


class TooLarge(Exception):
    pass


class Invalid(Exception):
    def __init__(self, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field


@dataclass
class Part:
    name: str
    path: Path
    size: int = 0


@dataclass
class UploadForm:
    """multipart/form-data into a scratch directory; runs in a worker thread, one chunk at a time.
    Refuses the 51st file part and a file part as it streams past 25 MB."""

    tmp: Path
    files: list[Part] = field(default_factory=list)
    fields: dict[str, str] = field(default_factory=dict)
    ended: bool = False
    _header: bytearray = field(default_factory=bytearray)
    _value: bytearray = field(default_factory=bytearray)
    _disposition: bytes = b""
    _field: str | None = None
    _data: bytearray = field(default_factory=bytearray)
    _out: IO[bytes] | None = None

    def callbacks(self) -> dict[str, Any]:
        return {
            "on_part_begin": self._begin,
            "on_header_field": lambda d, s, e: self._header.extend(d[s:e]),
            "on_header_value": lambda d, s, e: self._value.extend(d[s:e]),
            "on_header_end": self._header_end,
            "on_headers_finished": self._headers_done,
            "on_part_data": self._part_data,
            "on_part_end": self._part_end,
            "on_end": self._end,
        }

    def _begin(self) -> None:
        self._disposition, self._field, self._data = b"", None, bytearray()

    def _header_end(self) -> None:
        if bytes(self._header).lower() == b"content-disposition":
            self._disposition = bytes(self._value)
        self._header.clear()
        self._value.clear()

    def _headers_done(self) -> None:
        _, opts = parse_options_header(self._disposition)
        name = opts.get(b"name", b"").decode("utf-8", "replace")
        if name == "file":
            if b"filename" not in opts:
                raise Invalid("A file part needs a file name.", "file")
            if len(self.files) >= MAX_FILES:
                raise TooLarge
            raw = opts[b"filename"].decode("utf-8", "replace")
            part = Part(raw.replace("\\", "/").rsplit("/", 1)[-1], self.tmp / str(len(self.files)))
            self.files.append(part)
            self._out = part.path.open("wb")
        elif name in FIELDS and b"filename" not in opts:
            self._field = name
        else:
            raise Invalid("Unexpected form field.", name or None)

    def _part_data(self, data: bytes, start: int, end: int) -> None:
        if self._out is not None:
            part = self.files[-1]
            part.size += end - start
            if part.size > MAX_FILE_BYTES:
                raise TooLarge
            self._out.write(data[start:end])
        else:
            self._data.extend(data[start:end])
            if len(self._data) > MAX_FIELD_BYTES:
                raise Invalid("The field is too long.", self._field)

    def _part_end(self) -> None:
        if self._out is not None:
            self._out.close()
            self._out = None
        elif self._field is not None:
            self.fields[self._field] = self._data.decode("utf-8", "replace")

    def _end(self) -> None:
        self.ended = True

    def close(self) -> None:
        if self._out is not None:
            self._out.close()
            self._out = None


def _boundary(request: Request) -> bytes:
    kind, opts = parse_options_header(request.headers.get("content-type", ""))
    if kind != b"multipart/form-data" or not opts.get(b"boundary"):
        raise ApiFailure(415, "unsupported_media_type", "Send multipart/form-data.")
    return opts[b"boundary"]


async def read_upload(request: Request, tmp: Path) -> UploadForm:
    """C2 §5.1 item 1: over a limit → 413 before anything is written outside `tmp`."""
    boundary = _boundary(request)
    form = UploadForm(tmp)
    parser = MultipartParser(boundary, form.callbacks())
    try:
        async for chunk in request.stream():
            if chunk:
                await anyio.to_thread.run_sync(parser.write, chunk)
        await anyio.to_thread.run_sync(parser.finalize)
    except TooLarge:
        raise ApiFailure(413, "too_large", "The upload is over the limits.") from None
    except Invalid as e:
        raise ApiFailure(400, "invalid_request", str(e), field=e.field) from None
    except MultipartParseError:
        raise ApiFailure(400, "invalid_request", "The multipart body is malformed.") from None
    finally:
        form.close()
    if not form.ended:
        raise ApiFailure(400, "invalid_request", "The multipart body is incomplete.")
    if not form.files:
        raise ApiFailure(400, "invalid_request", "Send at least one file.", field="file")
    if form.fields.get("visitor", "false") not in ("true", "false"):
        raise ApiFailure(400, "invalid_request", "visitor is true or false.", field="visitor")
    if len(form.fields.get("title", "")) > MAX_TITLE:
        raise ApiFailure(400, "invalid_request", "The title is too long.", field="title")
    return form


def restore_ids(conn: Connection, document_ids: list[str]) -> dict[str, int]:
    """C7 §8.4: each trashed document's live `delete` entry (the one Restore undoes)."""
    if not document_ids:
        return {}
    f = T["file_ops"]
    rows = conn.execute(
        select(f.c.document_id, func.max(f.c.id))
        .where(f.c.document_id.in_(document_ids), f.c.action == "delete", f.c.fs_state == "done")
        .group_by(f.c.document_id)
    ).all()
    return dict(rows)  # type: ignore[arg-type]


def _item(row: Mapping[str, Any], deleted: bool, restore: dict[str, int]) -> dict[str, Any]:
    dup_deleted = row["outcome"] == "duplicate" and deleted
    return {
        "id": row["id"],
        "original_name": row["original_name"],
        "sha256": row["sha256"],
        "size_bytes": row["size_bytes"],
        "outcome": row["outcome"],
        "reject_reason": row["reject_reason"],
        "document_id": row["document_id"],
        "deleted": dup_deleted,
        "restore_journal_id": restore.get(row["document_id"]) if dup_deleted else None,
    }


def _intake_result(intake: Intake) -> dict[str, Any]:
    with get_sync_engine().connect() as conn:
        trashed = [i.document_id for i in intake.items if i.deleted and i.document_id]
        restore = restore_ids(conn, trashed)
        items = [
            _item(
                {"id": i.id, "original_name": i.original_name, "sha256": i.sha256,
                 "size_bytes": i.size_bytes, "outcome": i.outcome,
                 "reject_reason": i.reject_reason, "document_id": i.document_id},
                i.deleted, restore,
            )
            for i in intake.items
        ]  # fmt: skip
        return {"batch": views.batch_summary(conn, intake.batch_id), "items": items}


@router.post(
    "/intake", operation_id="uploadIntake", status_code=201, response_model=IntakeResult,
    responses=errors(400, 401, 403, 413, 415, 423), openapi_extra={"requestBody": UPLOAD_BODY},
)  # fmt: skip
async def upload(request: Request) -> dict[str, Any]:
    tmp = Path(await anyio.to_thread.run_sync(lambda: tempfile.mkdtemp(prefix="mona-upload-")))
    try:
        form = await read_upload(request, tmp)
        title = form.fields.get("title", "").strip() or None
        intake = await run(
            ingest_files, get_intake_ctx(), [Upload(p.path, p.name) for p in form.files],
            source="drop", visitor=form.fields.get("visitor") == "true", title=title,
        )  # fmt: skip
    finally:
        await anyio.to_thread.run_sync(lambda: shutil.rmtree(tmp, ignore_errors=True))
    return await run(_intake_result, intake)


# --- §5.2 batches ---


def _list(offset: int, limit: int) -> dict[str, Any]:
    b = T["batches"]
    with get_sync_engine().connect() as conn:
        total = conn.execute(select(func.count()).select_from(b)).scalar_one()
        ids = conn.execute(
            select(b.c.id).order_by(b.c.started_at.desc(), b.c.id.desc())
            .offset(offset).limit(limit)
        ).scalars().all()  # fmt: skip
        items = [views.batch_summary(conn, i) for i in ids]
    return {"items": [i for i in items if i], "total": total, "offset": offset, "limit": limit}


@router.get(
    "/batches", operation_id="listBatches", response_model=Page[BatchSummary],
    responses=errors(400, 401, 423),
)  # fmt: skip
async def list_batches(offset: Offset = 0, limit: PageLimit = 50) -> dict[str, Any]:
    return await run(_list, offset, limit)


def _detail(batch_id: str) -> dict[str, Any]:
    it, d = T["intake_items"], T["documents"]
    with get_sync_engine().connect() as conn:
        summary = views.batch_summary(conn, batch_id)
        if summary is None:
            raise ApiFailure(404, "not_found", "No batch with that id.")
        rows = conn.execute(
            select(it, d.c.deleted_at)
            .outerjoin(d, d.c.id == it.c.document_id)
            .where(it.c.batch_id == batch_id)
            .order_by(*UPLOAD_ORDER)
        ).mappings().all()  # fmt: skip
        trashed = [r["document_id"] for r in rows if r["deleted_at"] is not None]
        restore = restore_ids(conn, trashed)
        docs = {
            s.id: s
            for s in views.summaries(
                conn, registry.load(conn), [r["document_id"] for r in rows if r["document_id"]]
            )
        }
        items = [
            _item(r, r["deleted_at"] is not None, restore)
            | {"document": docs.get(r["document_id"])}
            for r in rows
        ]
    return {"batch": summary, "items": items}


@router.get(
    "/batches/{id}", operation_id="getBatch", response_model=BatchDetail,
    responses=errors(401, 404, 423),
)  # fmt: skip
async def get_batch(batch_id: BatchId, request: Request) -> Response:
    return polled(request, BatchDetail, await run(_detail, batch_id))


def _rename(batch_id: str, title: str | None) -> dict[str, Any]:
    b = T["batches"]
    with get_sync_engine().begin() as conn:
        done = conn.execute(update(b).where(b.c.id == batch_id).values(title=title)).rowcount
        if not done:
            raise ApiFailure(404, "not_found", "No batch with that id.")
        return views.batch_summary(conn, batch_id)  # type: ignore[return-value]


@router.patch(
    "/batches/{id}", operation_id="patchBatch", response_model=BatchSummary,
    responses=errors(400, 401, 403, 404, 413, 415, 423),
)  # fmt: skip
async def patch_batch(batch_id: BatchId, body: BatchPatch) -> dict[str, Any]:
    title = body.title.strip() if body.title else None
    return await run(_rename, batch_id, title or None)

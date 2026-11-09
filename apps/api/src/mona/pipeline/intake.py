"""Intake (C1 §4.1, C7 §8.4): dedupe by sha256 among live documents (A24), place in the inbox,
queue `extract_text`."""

import hashlib
import os
import subprocess
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import Connection, exists, insert, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from mona.fileops import inbox_name, lock_sha256, resolve_inside
from mona.ids import new_id
from mona.pipeline.extract import Runner, page_count, run
from mona.pipeline.queue import defer
from mona.services.context import Ctx
from mona.services.errors import ServiceError
from mona.services.pipeline import finish_batch_if_done, settle_hooks
from mona.services.registry import T

MAX_BYTES = 25 * 1024 * 1024
PDF_TAIL = 1024
MAGIC = ((b"%PDF-", "application/pdf"), (b"\xff\xd8\xff", "image/jpeg"),
         (b"\x89PNG\r\n\x1a\n", "image/png"))  # fmt: skip


@dataclass(frozen=True)
class Upload:
    content: bytes | Path
    original_name: str


@dataclass
class IntakeItem:
    id: str
    original_name: str
    sha256: str
    size_bytes: int
    outcome: str
    document_id: str | None = None
    reject_reason: str | None = None
    deleted: bool = False


@dataclass
class Intake:
    batch_id: str
    items: list[IntakeItem] = field(default_factory=list)
    batch_done: bool = False


def sniff(data: bytes) -> str | None:
    return next((mime for magic, mime in MAGIC if data.startswith(magic)), None)


def _entropy_end(data: bytes, i: int) -> int:
    """The next marker after entropy-coded data (stuffed 0xFF00 and restarts skipped), or -1."""
    while True:
        i = data.find(b"\xff", i)
        if i < 0 or i + 1 >= len(data):
            return -1
        m = data[i + 1]
        if m == 0 or 0xD0 <= m <= 0xD7:
            i += 2
        elif m == 0xFF:
            i += 1
        else:
            return i


def _jpeg_complete(data: bytes) -> bool:
    """Segments from SOI reach EOI; bytes after EOI (a phone's appended video) are ignored."""
    i, n = 2, len(data)
    while i + 1 < n:
        if data[i] != 0xFF:
            return False
        m = data[i + 1]
        if m == 0xFF:
            i += 1
        elif m == 0xD9:
            return True
        elif m == 0x01 or 0xD0 <= m <= 0xD7:
            i += 2
        elif i + 4 > n:
            return False
        else:
            i += 2 + int.from_bytes(data[i + 2 : i + 4], "big")
            if m == 0xDA and (i := _entropy_end(data, i)) < 0:
                return False
    return False


def _png_complete(data: bytes) -> bool:
    i, n = len(MAGIC[2][0]), len(data)
    while i + 8 <= n:
        size, kind = int.from_bytes(data[i : i + 4], "big"), data[i + 4 : i + 8]
        i += 12 + size
        if kind == b"IEND":
            return i <= n
    return False


def _pdf_opens(data: bytes, runner: Runner) -> bool:
    if b"%%EOF" in data[-PDF_TAIL:]:
        return True
    with tempfile.NamedTemporaryFile(prefix="mona-intake-", suffix=".pdf") as f:
        f.write(data)
        f.flush()
        try:
            return page_count(Path(f.name), runner) > 0
        except FileNotFoundError:
            return True
        except (subprocess.SubprocessError, ValueError, OSError):
            return False


def intact(data: bytes, mime: str, runner: Runner = run) -> bool:
    """C2 §5.1: the bytes open. A truncated image misses its end; a PDF without its `%%EOF`
    trailer must still open in poppler with a page."""
    if mime == "image/jpeg":
        return _jpeg_complete(data)
    if mime == "image/png":
        return _png_complete(data)
    return _pdf_opens(data, runner)


def create_batch(
    conn: Connection, *, source: str, visitor: bool = False, title: str | None = None, now=None
) -> str:
    """A running batch and its one `intake_batch` group, in the caller's transaction."""
    b = new_id("bat")
    started = {"started_at": now} if now else {}
    conn.execute(
        insert(T["batches"]).values(id=b, source=source, visitor=visitor, title=title, **started)
    )
    conn.execute(
        insert(T["op_groups"]).values(
            id=new_id("grp"), kind="intake_batch", actor="mona", via="pipeline", batch_id=b
        )
    )
    return b


def _read(u: Upload) -> bytes | None:
    if isinstance(u.content, bytes):
        return u.content
    try:
        return Path(u.content).read_bytes()
    except OSError:
        return None


def _write_inbox(inbox: Path, name: str, data: bytes) -> Path:
    path = resolve_inside(inbox, name)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
    try:
        view, done = memoryview(data), 0
        while done < len(view):
            done += os.write(fd, view[done:])
        os.fsync(fd)
    finally:
        os.close(fd)
    return path


def ingest_files(
    ctx: Ctx,
    uploads: Sequence[Upload],
    *,
    source: str = "drop",
    visitor: bool = False,
    title: str | None = None,
    batch_id: str | None = None,
) -> Intake:
    """One batch per call (or an existing running one); jobs are queued in upload order after
    every row exists, so no document can finish the batch while the rest are still arriving."""
    if source not in ("drop", "telegram"):
        raise ServiceError("invalid_argument", "source must be drop or telegram.", field="source")
    it = T["intake_items"]
    now = ctx.clock()
    checked = [_check(u) for u in uploads]
    written: list[Path] = []
    try:
        with settle_hooks(ctx), ctx.engine.begin() as conn:
            if batch_id is None:
                batch_id = create_batch(conn, source=source, visitor=visitor, title=title, now=now)
            else:
                row = conn.execute(
                    select(T["batches"]).where(T["batches"].c.id == batch_id)
                    .with_for_update(key_share=True)
                ).mappings().first()  # fmt: skip
                if row is None:
                    raise ServiceError("not_found", f"Unknown batch {batch_id}.")
                if row["status"] != "running":
                    raise ServiceError("conflict", "The batch is already done.")
                visitor = row["visitor"]
            visitors = None
            if visitor:
                e = T["entities"]
                visitors = conn.execute(
                    select(e.c.id).where(e.c.purge_after_hours.isnot(None))
                ).scalar()
            for sha in sorted({item.sha256 for item, mime in checked if mime}):
                lock_sha256(conn, sha)
            out = Intake(batch_id)
            for u, (item, mime) in zip(uploads, checked, strict=True):
                if mime:
                    _place(ctx, conn, u, item, mime, batch_id, source, visitors, now, written)
                conn.execute(
                    insert(it).values(
                        id=item.id, batch_id=batch_id, original_name=item.original_name,
                        sha256=item.sha256, size_bytes=item.size_bytes, outcome=item.outcome,
                        document_id=item.document_id, reject_reason=item.reject_reason,
                    )
                )  # fmt: skip
                out.items.append(item)
            for item in out.items:
                if item.outcome == "accepted" and item.document_id:
                    defer(conn, "extract_text", item.document_id)
            out.batch_done = finish_batch_if_done(conn, batch_id, now, settled=False)
    except BaseException:
        for p in written:
            p.unlink(missing_ok=True)
        raise
    return out


def ingest_file(
    ctx: Ctx,
    content: bytes | Path,
    original_name: str,
    *,
    source: str = "drop",
    visitor: bool = False,
    batch_id: str | None = None,
) -> Intake:
    """One file: its own batch unless `batch_id` names a running one (then use `ingest_files`
    for several files, so the batch can't finish between two of them)."""
    return ingest_files(
        ctx, [Upload(content, original_name)], source=source, visitor=visitor, batch_id=batch_id
    )


def _check(u: Upload) -> tuple[IntakeItem, str | None]:
    """Before the transaction: a `rejected` item, or the sniffed type of bytes that open."""
    name = (u.original_name or "document").strip()[:255] or "document"
    data = _read(u)
    item = IntakeItem(new_id("itm"), name, hashlib.sha256(data or b"").hexdigest(),
                      len(data or b""), "rejected")  # fmt: skip
    mime = None
    if data is None:
        item.reject_reason = "unreadable_file"
    elif not data:
        item.reject_reason = "empty"
    elif len(data) > MAX_BYTES:
        item.reject_reason = "too_large"
    elif (mime := sniff(data)) is None:
        item.reject_reason = "unsupported_type"
    elif not intact(data, mime):
        item.reject_reason, mime = "unreadable_file", None
    return item, mime


def _twin(conn: Connection, sha256: str):
    """A24 dedupe: a live document with these bytes, or a deleted one whose restore is pending."""
    d, f = T["documents"], T["file_ops"]
    restoring = exists().where(
        f.c.document_id == d.c.id,
        f.c.fs_state == "pending",
        f.c.after["location"].astext != "trash",
    )
    return conn.execute(
        select(d.c.id, d.c.location)
        .where(d.c.sha256 == sha256, or_(d.c.deleted_at.is_(None), restoring))
        .order_by(d.c.deleted_at.is_not(None)).limit(1)
    ).first()  # fmt: skip


def _place(
    ctx: Ctx,
    conn: Connection,
    u: Upload,
    item: IntakeItem,
    mime: str,
    batch_id: str,
    source: str,
    visitors: str | None,
    now,
    written: list[Path],
) -> None:
    """Under the sha256 lock (A37): `duplicate` of the twin, else the inbox file and its row."""
    d = T["documents"]
    existing = _twin(conn, item.sha256)
    if existing is not None:
        item.outcome, item.document_id = "duplicate", existing.id
        item.deleted = existing.location == "trash"
        return
    data = _read(u)
    if data is None or hashlib.sha256(data).hexdigest() != item.sha256:
        item.reject_reason = "unreadable_file"
        return
    doc_id = new_id("doc")
    rel = inbox_name(doc_id, mime)
    written.append(_write_inbox(ctx.ops.roots.inbox, rel, data))
    inserted = conn.execute(
        pg_insert(d)
        .values(
            id=doc_id, sha256=item.sha256, original_name=item.original_name, mime_type=mime,
            size_bytes=len(data), source=source, batch_id=batch_id, arrived_at=now,
            location="inbox", current_path=rel, status="processing", pipeline_stage="queued",
            entity_id=visitors, created_at=now, updated_at=now,
        )
        .on_conflict_do_nothing(index_elements=["sha256"], index_where=d.c.deleted_at.is_(None))
        .returning(d.c.id)
    ).scalar()  # fmt: skip
    if inserted is None:
        written.pop().unlink(missing_ok=True)
        other = conn.execute(
            select(d.c.id, d.c.location).where(d.c.sha256 == item.sha256, d.c.deleted_at.is_(None))
        ).one()
        item.outcome, item.document_id = "duplicate", other.id
        item.deleted = other.location == "trash"
        return
    item.outcome, item.document_id = "accepted", doc_id

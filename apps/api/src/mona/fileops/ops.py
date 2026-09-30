"""C7 §4 atomic moves with their journal entry, §5 undo and redo, §4.3 crash recovery."""

import errno
import hashlib
import os
import re
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import Connection, Engine, insert, select, text, update
from sqlalchemy.exc import IntegrityError

from mona.fileops.errors import FileOpError, ForbiddenPath, SimulatedCrash
from mona.fileops.roots import Roots, resolve_inside
from mona.fileops.state import (
    UNDOABLE,
    T,
    chain,
    doc_state,
    entry,
    group_entries,
    iso,
    undo_state,
    without_adoption,
)
from mona.ids import new_id
from mona.templates.render import EXTENSIONS

LOCK = text("SELECT pg_advisory_lock(hashtextextended(:k, 0))")
UNLOCK = text("SELECT pg_advisory_unlock(hashtextextended(:k, 0))")
MAX_SUFFIX = 999
REVIEW = ("review", "unreadable")
KEEP: Any = object()

Action = Literal["file", "move", "rename", "unfile", "delete"]
CrashPoint = Literal["after_a", "after_b1", "after_b3", "in_c"]
Hook = Callable[[Connection, Mapping[str, Any], Mapping[str, Any]], None]
FailHook = Callable[[Connection, Mapping[str, Any], Mapping[str, Any], str], None]


def error_code(err: BaseException) -> str:
    """The errno name, the FileOpError hint or code, else the class name (C5 §1.2)."""
    if isinstance(err, FileOpError):
        return err.hint or err.code
    return errno.errorcode.get(getattr(err, "errno", None) or 0, type(err).__name__)


def utcnow() -> datetime:
    return datetime.now(UTC)


def sha256_file(path: Path) -> str | None:
    """The file's sha256, or None when nothing regular is there."""
    try:
        if not os.path.isfile(path) or os.path.islink(path):
            return None
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def suffixed(rel: str, n: int) -> str:
    """C7 §8.1: `-N` appended to the stem, before the extension."""
    head, _, name = rel.rpartition("/")
    stem, dot, ext = name.rpartition(".")
    if not dot or not stem:
        stem, ext = name, ""
    out = f"{stem}-{n}" + (f".{ext}" if ext else "")
    return f"{head}/{out}" if head else out


def is_suffix_of(current: str, target: str) -> bool:
    """True if `current` is `target` or one of its §8.1 suffixed names."""
    if current == target:
        return True
    head, _, name = target.rpartition("/")
    stem, dot, ext = name.rpartition(".")
    if not dot or not stem:
        stem, ext = name, ""
    pattern = re.escape(stem) + r"-([2-9]|[1-9][0-9]{1,2})" + (re.escape("." + ext) if ext else "")
    chead, _, cname = current.rpartition("/")
    return chead == head and re.fullmatch(pattern, cname) is not None


def inbox_name(document_id: str, mime_type: str) -> str:
    return document_id + EXTENSIONS[mime_type]


class Fs:
    """Filesystem primitives of step B; tests substitute failures."""

    def link(self, src: Path, dst: Path) -> None:
        os.link(src, dst, follow_symlinks=False)

    def unlink(self, path: Path) -> None:
        os.unlink(path)

    def fsync_dir(self, path: Path) -> None:
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


@dataclass(frozen=True)
class Change:
    """A requested move of one document (C7 §4.2), computed from `expected`."""

    document_id: str
    action: Action
    location: str
    path: str
    actor: str
    via: str
    expected: tuple[str, str]
    status: str | None = None
    reasons: tuple[str, ...] | None = None
    classification_id: Any = KEEP
    rule_id: Any = KEEP
    group_id: str | None = None
    batch_id: str | None = None
    entry_rule_id: str | None = None
    confidence: int | None = None
    band: str | None = None
    resolution: str = "refiled"


@dataclass
class Result:
    outcome: Literal["moved", "unchanged"]
    document_id: str
    entry_id: int | None = None
    state: dict[str, Any] | None = None


@dataclass
class UndoResult:
    """`state` is `done` or why nothing changed (C7 §5.3, C4 §3.16 `skipped`)."""

    journal_id: int
    state: Literal["done", "superseded", "already_undone", "not_undoable", "not_allowed"]
    entry_id: int | None = None
    document_id: str | None = None
    after: dict[str, Any] | None = None


@dataclass
class GroupUndoResult:
    group_id: str | None
    undone: list[UndoResult] = field(default_factory=list)
    skipped: list[UndoResult] = field(default_factory=list)
    state: Literal["done", "already_undone", "not_undoable"] = "done"


@dataclass
class _Plan:
    document_id: str
    action: str
    actor: str
    via: str
    expected: tuple[str, str]
    before: dict[str, Any]
    after: dict[str, Any]
    undo_of: int | None = None
    group_id: str | None = None
    batch_id: str | None = None
    rule_id: str | None = None
    confidence: int | None = None
    band: str | None = None
    resolution: str = "refiled"


@contextmanager
def tx(conn: Connection) -> Iterator[Connection]:
    """A fresh transaction on `conn`, ending any autobegun read first."""
    if conn.in_transaction():
        conn.rollback()
    with conn.begin():
        yield conn


class FileOps:
    """The one library that renames, moves or deletes document files (C7)."""

    def __init__(
        self,
        engine: Engine,
        roots: Roots,
        *,
        clock: Callable[[], datetime] = utcnow,
        fs: Fs | None = None,
        on_commit: Hook | None = None,
        on_failed: FailHook | None = None,
    ):
        self.engine = engine
        self.roots = roots
        self.clock = clock
        self.fs = fs or Fs()
        self.on_commit = on_commit
        self.on_failed = on_failed
        self.crash_at: CrashPoint | None = None

    # --- plumbing ---

    def _crash(self, point: CrashPoint) -> None:
        if self.crash_at == point:
            raise SimulatedCrash(point)

    @contextmanager
    def locked(self, document_id: str) -> Iterator[Connection]:
        """C7 §4.1: the per-document advisory lock, held on one dedicated connection."""
        with self.engine.connect() as conn:
            conn.execute(LOCK, {"k": document_id})
            conn.commit()
            try:
                yield conn
            finally:
                if conn.in_transaction():
                    conn.rollback()
                conn.execute(UNLOCK, {"k": document_id})
                conn.commit()

    def _doc(self, conn: Connection, document_id: str) -> Mapping[str, Any]:
        d = T["documents"]
        row = conn.execute(select(d).where(d.c.id == document_id)).mappings().first()
        if row is None:
            raise FileOpError("not_found", f"unknown document {document_id}")
        return row

    def _src(self, state: Mapping[str, Any]) -> tuple[Path, str]:
        if state.get("adopted"):
            return self.roots.trash, state["trash_copy"]
        return self.roots.root(state["location"]), state["path"]

    def _dst(self, state: Mapping[str, Any]) -> tuple[Path, str]:
        if state.get("adopted"):
            return self.roots.trash, state["trash_copy"]
        return self.roots.root(state["location"]), state["path"]

    def _set_after(self, conn: Connection, entry_id: int, after: dict[str, Any]) -> None:
        with tx(conn):
            f = T["file_ops"]
            conn.execute(update(f).where(f.c.id == entry_id).values(after=after))

    def _mark_failed(self, conn: Connection, e: Mapping[str, Any], code: str) -> None:
        f = T["file_ops"]
        conn.execute(update(f).where(f.c.id == e["id"]).values(fs_state="failed"))
        if self.on_failed:
            self.on_failed(conn, e, self._doc(conn, e["document_id"]), code)

    # --- target names (§8) ---

    def _free_name(
        self, doc: Mapping[str, Any], location: str, rel: str, start: int = 1
    ) -> tuple[str, bool]:
        """(path, identical): the first name from `start` that is free, this document's own,
        or (archive only) holds identical bytes (§8.3)."""
        root = self.roots.root(location)
        for n in range(start, MAX_SUFFIX + 1):
            cand = rel if n == 1 else suffixed(rel, n)
            if (doc["location"], doc["current_path"]) == (location, cand):
                return cand, False
            path = resolve_inside(root, cand, taken_ok=True)
            if not os.path.lexists(path):
                return cand, False
            if location == "archive" and sha256_file(path) == doc["sha256"]:
                return cand, True
        raise FileOpError("conflict", "no free name after -999", hint="collision_exhausted")

    def _suffix_number(self, rel: str, base: str) -> int:
        if rel == base:
            return 1
        stem = rel.rpartition("/")[2].rpartition(".")[0] or rel.rpartition("/")[2]
        return int(stem.rpartition("-")[2])

    # --- the A–D operation ---

    def _plan_change(self, conn: Connection, doc: Mapping[str, Any], c: Change) -> _Plan:
        now = self.clock()
        before = doc_state(doc)
        status = c.status or doc["status"]
        after = {
            "location": c.location,
            "path": c.path,
            "status": status,
            "reasons": list(c.reasons if c.reasons is not None else doc["reasons"]),
            "classification_id": (
                doc["classification_id"] if c.classification_id is KEEP else c.classification_id
            ),
            "rule_id": doc["rule_id"] if c.rule_id is KEEP else c.rule_id,
            "filed_by": None,
            "filed_at": None,
        }
        if c.action in ("file", "move", "rename") and c.location == "archive":
            after["filed_by"], after["filed_at"] = c.actor, iso(now)
        elif c.action == "delete":
            after["filed_by"], after["filed_at"] = before["filed_by"], before["filed_at"]
        return _Plan(
            document_id=c.document_id,
            action=c.action,
            actor=c.actor,
            via=c.via,
            expected=c.expected,
            before=before,
            after=after,
            group_id=c.group_id,
            batch_id=c.batch_id,
            rule_id=c.entry_rule_id,
            confidence=c.confidence,
            band=c.band,
            resolution=c.resolution,
        )

    def move(self, c: Change) -> Result:
        """One A–D operation; raises FileOpError (`conflict`/`stale`, `not_allowed`,
        `forbidden_path`, `conflict`/errno) with nothing changed, or after rolling back."""
        with self.locked(c.document_id) as conn:
            self._recover_document(conn, c.document_id)
            doc = self._doc(conn, c.document_id)
            conn.rollback()
            return self._run(conn, doc, self._plan_change(conn, doc, c))

    def _run(self, conn: Connection, doc: Mapping[str, Any], plan: _Plan) -> Result:
        # A. intent
        if (doc["location"], doc["current_path"]) != plan.expected:
            raise FileOpError("conflict", "the document moved meanwhile", hint="stale")
        if plan.actor == "mona" and plan.after["location"] == "trash":
            raise FileOpError("not_allowed", "Mona never moves a document to the trash")
        target = without_adoption(plan.after)
        src_root, src_rel = self._src(plan.before)
        resolve_inside(src_root, src_rel)
        base = target["path"]
        rel, identical = self._free_name(doc, target["location"], base)
        if (doc["location"], doc["current_path"]) == (target["location"], rel):
            return Result("unchanged", doc["id"])
        resolve_inside(self.roots.root(target["location"]), rel, create=True, taken_ok=True)
        target["path"] = rel
        if plan.after.get("status") == "processing":
            target["status"] = "review"
            target["reasons"] = target["reasons"] or ["low"]
        f = T["file_ops"]
        try:
            with tx(conn):
                entry_id = conn.execute(
                    insert(f)
                    .values(
                        at=self.clock(),
                        actor=plan.actor,
                        via=plan.via,
                        action=plan.action,
                        document_id=doc["id"],
                        sha256=doc["sha256"],
                        before=plan.before,
                        after=target,
                        fs_state="pending",
                        batch_id=plan.batch_id,
                        group_id=plan.group_id,
                        rule_id=plan.rule_id,
                        confidence=plan.confidence,
                        band=plan.band,
                        undoable=plan.action in UNDOABLE,
                        undo_of=plan.undo_of,
                    )
                    .returning(f.c.id)
                ).scalar_one()
        except IntegrityError as err:
            if "file_ops_undo_of_live" in str(err.orig):
                raise FileOpError("already_undone", "already undone") from None
            raise
        self._crash("after_a")
        # B. filesystem
        src = src_root / src_rel
        try:
            dst, target = self._link(conn, entry_id, doc, src, target, base, identical)
            self._crash("after_b1")
            self.fs.fsync_dir(dst.parent)
            self.fs.unlink(src)
            self.fs.fsync_dir(src.parent)
            self._crash("after_b3")
        except Exception as err:
            code = error_code(err)
            if self._cleanup(conn, entry_id, doc, src, code):
                return Result("moved", doc["id"], entry_id, entry(conn, entry_id)["after"])
            if code == "forbidden_path":
                raise
            raise FileOpError("conflict", f"filesystem error {code}", hint=code) from None
        # C. commit
        self._commit(conn, entry_id, plan.resolution)
        # D. tidy
        if plan.before["location"] == "archive" and not plan.before.get("adopted"):
            self._tidy(self.roots.archive, src.parent)
        return Result("moved", doc["id"], entry_id, target)

    def _link(
        self,
        conn: Connection,
        entry_id: int,
        doc: Mapping[str, Any],
        src: Path,
        target: dict[str, Any],
        base: str,
        identical: bool,
    ) -> tuple[Path, dict[str, Any]]:
        """B1: link, taking the next suffix on EEXIST, adopting identical bytes (§8.3)."""
        root = self.roots.root(target["location"])
        retried = False
        while True:
            if identical:
                target = self._adopt(conn, entry_id, doc, target)
            dst_root, dst_rel = self._dst(target)
            dst = resolve_inside(dst_root, dst_rel, create=True)
            try:
                self.fs.link(src, dst)
                return dst, target
            except FileExistsError:
                if target.get("adopted"):
                    raise FileOpError("conflict", "trash copy name taken", hint="EEXIST") from None
                if target["location"] == "archive" and sha256_file(dst) == doc["sha256"]:
                    identical = True
                    continue
                n = self._suffix_number(target["path"], base) + 1
                rel, identical = self._free_name(doc, target["location"], base, n)
                target = {**target, "path": rel}
                resolve_inside(root, rel, create=True, taken_ok=True)
                self._set_after(conn, entry_id, target)
            except FileNotFoundError:
                if retried or not os.path.lexists(src):
                    raise
                retried = True

    def _adopt(
        self, conn: Connection, entry_id: int, doc: Mapping[str, Any], target: dict[str, Any]
    ) -> dict[str, Any]:
        d = T["documents"]
        owner = conn.execute(
            select(d.c.id).where(
                d.c.location == target["location"], d.c.current_path == target["path"]
            )
        ).first()
        if owner is not None:
            raise RuntimeError("identical bytes at the target belong to another document")
        name = target["path"].rpartition("/")[2]
        copy, _ = self._free_trash(doc, f"{doc['id']}/{name}")
        target = {**target, "adopted": True, "trash_copy": copy}
        self._set_after(conn, entry_id, target)
        return target

    def _free_trash(self, doc: Mapping[str, Any], rel: str) -> tuple[str, bool]:
        for n in range(1, MAX_SUFFIX + 1):
            cand = rel if n == 1 else suffixed(rel, n)
            if not os.path.lexists(resolve_inside(self.roots.trash, cand, taken_ok=True)):
                return cand, False
        raise FileOpError("conflict", "no free trash name", hint="collision_exhausted")

    def _cleanup(
        self, conn: Connection, entry_id: int, doc: Mapping[str, Any], src: Path, code: str
    ) -> bool:
        """After a step-B/C error: roll back, or finish (True) if the move had completed."""
        try:
            e = entry(conn, entry_id)
            dst_root, dst_rel = self._dst(e["after"])
            dst = dst_root / dst_rel
            if os.path.lexists(dst) and os.path.lexists(src) and os.path.samefile(src, dst):
                self.fs.unlink(dst)
            elif not os.path.lexists(src) and sha256_file(dst) == doc["sha256"]:
                self._commit(conn, entry_id, "refiled")
                return True
            with tx(conn):
                self._mark_failed(conn, e, code)
        except SimulatedCrash:
            raise
        except Exception:
            if conn.in_transaction():
                conn.rollback()
        return False

    def _commit(self, conn: Connection, entry_id: int, resolution: str) -> None:
        """Step C: the document follows `after`, the entry turns `done`, in one transaction."""
        f, d = T["file_ops"], T["documents"]
        with tx(conn):
            e = conn.execute(select(f).where(f.c.id == entry_id).with_for_update()).mappings().one()
            a = e["after"]
            now = self.clock()
            values: dict[str, Any] = {
                "location": a["location"],
                "current_path": a["path"],
                "status": a["status"],
                "reasons": a["reasons"],
                "classification_id": a["classification_id"],
                "rule_id": a["rule_id"],
                "filed_by": a["filed_by"],
                "filed_at": datetime.fromisoformat(a["filed_at"]) if a["filed_at"] else None,
                "filed_op_id": entry_id,
                "updated_at": now,
            }
            old = self._doc(conn, e["document_id"])
            if a["location"] == "trash":
                values["deleted_at"] = old["deleted_at"] or now
            else:
                values["deleted_at"] = None
            values |= self._classified(conn, a["classification_id"], old)
            conn.execute(update(d).where(d.c.id == e["document_id"]).values(**values))
            conn.execute(update(f).where(f.c.id == entry_id).values(fs_state="done"))
            if e["undo_of"] is not None:
                conn.execute(update(f).where(f.c.id == e["undo_of"]).values(undone_by=entry_id))
            new = self._doc(conn, e["document_id"])
            keep_review(conn, new, resolution, e["actor"], now)
            if self.on_commit:
                self.on_commit(conn, e, new)
            self._crash("in_c")

    def _classified(
        self, conn: Connection, cls_id: str | None, doc: Mapping[str, Any]
    ) -> dict[str, Any]:
        """The fields a classification pointer implies (C7 §2.2, §4.2 C.1)."""
        from mona.templates import EntityInfo, document_fiscal_year

        cols = ("entity_id", "sub_unit_id", "category_id", "subcategory_key", "counterparty_id")
        if cls_id is None:
            return {}
        c = T["classifications"]
        row = conn.execute(select(c).where(c.c.id == cls_id)).mappings().one()
        out: dict[str, Any] = {k: row[k] for k in cols}
        out["confidence"], out["band"] = row["confidence"], row["band"]
        ent = None
        if row["entity_id"]:
            e = T["entities"]
            er = conn.execute(select(e).where(e.c.id == row["entity_id"])).mappings().one()
            ent = EntityInfo(er["key"], er["folder_name"], er["fy_end_month"], er["fy_end_day"])
        out["fiscal_year"] = document_fiscal_year(
            ent, doc["period_end"], doc["doc_date"], doc["arrived_at"]
        )
        return out

    def _tidy(self, root: Path, start: Path) -> None:
        """Step D: remove now-empty parents, never the root."""
        p = start
        while p != root and str(p).startswith(str(root) + "/"):
            try:
                os.rmdir(p)
            except OSError:
                return
            p = p.parent

    # --- recovery (§4.3) ---

    def _recover_document(self, conn: Connection, document_id: str) -> None:
        f = T["file_ops"]
        ids = (
            conn.execute(
                select(f.c.id)
                .where(f.c.document_id == document_id, f.c.fs_state == "pending")
                .order_by(f.c.id)
            )
            .scalars()
            .all()
        )
        conn.rollback()
        for eid in ids:
            self._recover_entry(conn, eid)

    def recover_pending(self, older_than: timedelta = timedelta(0)) -> dict[int, str]:
        """Resolve every `pending` entry older than `older_than`, oldest first."""
        f = T["file_ops"]
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(f.c.id, f.c.document_id)
                .where(f.c.fs_state == "pending", f.c.at <= self.clock() - older_than)
                .order_by(f.c.id)
            ).all()
        out: dict[int, str] = {}
        for eid, doc_id in rows:
            with self.locked(doc_id) as conn:
                out[eid] = self._recover_entry(conn, eid)
        return out

    def _recover_entry(self, conn: Connection, entry_id: int) -> str:
        f = T["file_ops"]
        with tx(conn):
            e = conn.execute(select(f).where(f.c.id == entry_id).with_for_update()).mappings().one()
            if e["fs_state"] != "pending":
                return "skipped"
            doc = self._doc(conn, e["document_id"])
            b, a = e["before"], e["after"]
            if (doc["location"], doc["current_path"]) != (b["location"], b["path"]):
                self._mark_failed(conn, e, "stale")
                return "failed"
            src_root, src_rel = self._src(b)
            dst_root, dst_rel = self._dst(a)
            src, dst = src_root / src_rel, dst_root / dst_rel
            s_ok, d_ok = os.path.lexists(src), os.path.lexists(dst)
            adopted_ok = (
                not a.get("adopted")
                or sha256_file(self.roots.root(a["location"]) / a["path"]) == doc["sha256"]
            )
            if s_ok and not d_ok:
                self._mark_failed(conn, e, "interrupted")
                return "failed"
            if s_ok and os.path.samefile(src, dst) and adopted_ok:
                finish = "unlink"
            elif s_ok:
                self._mark_failed(conn, e, "EEXIST")
                return "failed"
            elif d_ok and sha256_file(dst) == doc["sha256"] and adopted_ok:
                finish = "commit"
            else:
                d = T["documents"]
                conn.execute(
                    update(d).where(d.c.id == doc["id"]).values(pipeline_error="missing_file")
                )
                self._mark_failed(conn, e, "missing_file")
                return "failed"
        if finish == "unlink":
            self.fs.unlink(src)
            self.fs.fsync_dir(src.parent)
        self._commit(conn, entry_id, "refiled")
        if b["location"] == "archive" and not b.get("adopted"):
            self._tidy(self.roots.archive, src.parent)
        return "done"

    # --- undo and redo (§5) ---

    def undo(
        self, journal_id: int, *, actor: str, via: str, group_id: str | None = None
    ) -> UndoResult:
        """C7 §5.3: reverse `tip(e)`; refusals change nothing and say why."""
        with self.engine.connect() as conn:
            e = entry(conn, journal_id)
        if e is None or e["fs_state"] != "done":
            raise FileOpError("not_found", f"unknown journal entry {journal_id}")
        if e["action"] not in UNDOABLE or e["document_id"] is None:
            return UndoResult(journal_id, "not_undoable", document_id=e["document_id"])
        with self.locked(e["document_id"]) as conn:
            self._recover_document(conn, e["document_id"])
            doc = self._doc(conn, e["document_id"])
            e = entry(conn, journal_id)
            state = undo_state(conn, e, doc)
            if state != "undoable":
                conn.rollback()
                return UndoResult(journal_id, state, document_id=doc["id"])  # type: ignore[arg-type]
            t = chain(conn, e)[-1]
            conn.rollback()
            plan = _Plan(
                document_id=doc["id"],
                action="redo" if t["action"] == "undo" else "undo",
                actor=actor,
                via=via,
                expected=(t["after"]["location"], t["after"]["path"]),
                before=dict(t["after"]),
                after=dict(t["before"]),
                undo_of=t["id"],
                group_id=group_id,
                rule_id=t["rule_id"],
            )
            try:
                r = self._run(conn, doc, plan)
            except FileOpError as err:
                if err.code in ("not_allowed", "already_undone"):
                    return UndoResult(journal_id, err.code, document_id=doc["id"])  # type: ignore[arg-type]
                raise
            if r.outcome == "unchanged":
                return UndoResult(journal_id, "superseded", document_id=doc["id"])
            return UndoResult(journal_id, "done", r.entry_id, doc["id"], r.state)

    def undo_group(self, group_id: str, *, actor: str, via: str) -> GroupUndoResult:
        """C7 §5.4: reverse journal order; skipped entries are reported with their state."""
        g = T["op_groups"]
        with self.engine.connect() as conn:
            grp = conn.execute(select(g).where(g.c.id == group_id)).mappings().first()
            if grp is None:
                raise FileOpError("not_found", f"unknown group {group_id}")
            entries = group_entries(conn, group_id)
            states = [undo_state(conn, e) for e in entries]
        if "undoable" not in states:
            state = "already_undone" if "undone" in states else "not_undoable"
            return GroupUndoResult(None, state=state)
        new_group = new_id("grp")
        with self.engine.begin() as conn:
            conn.execute(
                insert(g).values(
                    id=new_group,
                    kind="redo" if grp["kind"] == "undo" else "undo",
                    actor=actor,
                    via=via,
                    rule_id=grp["rule_id"],
                    target_group_id=group_id,
                )
            )
        out = GroupUndoResult(new_group)
        for e in entries:
            r = self.undo(e["id"], actor=actor, via=via, group_id=new_group)
            (out.undone if r.state == "done" else out.skipped).append(r)
        return out

    # --- delete (§7) ---

    def delete(
        self, document_id: str, *, actor: str, via: str, expected: tuple[str, str] | None = None
    ) -> Result:
        """C7 §7: an A–C move to `trash/<id>/<basename>`; refused for Mona."""
        with self.engine.connect() as conn:
            doc = self._doc(conn, document_id)
        if doc["location"] == "trash":
            return Result("unchanged", document_id)
        basename = doc["current_path"].rpartition("/")[2]
        return self.move(
            Change(
                document_id=document_id,
                action="delete",
                location="trash",
                path=f"{document_id}/{basename}",
                actor=actor,
                via=via,
                expected=expected or (doc["location"], doc["current_path"]),
                resolution="deleted",
            )
        )


def keep_review(
    conn: Connection, doc: Mapping[str, Any], resolution: str, actor: str, now: datetime
) -> None:
    """C1 §4.5: a non-deleted document has an open review item iff it is in review."""
    r = T["review_items"]
    open_item = (
        conn.execute(select(r).where(r.c.document_id == doc["id"], r.c.status == "open"))
        .mappings()
        .first()
    )
    want = doc["status"] in REVIEW and doc["deleted_at"] is None
    if want and open_item is None:
        conn.execute(
            insert(r).values(
                id=new_id("rev"), document_id=doc["id"], reasons=list(doc["reasons"]) or ["low"]
            )
        )
    elif want and doc["reasons"] and list(open_item["reasons"]) != list(doc["reasons"]):
        conn.execute(update(r).where(r.c.id == open_item["id"]).values(reasons=doc["reasons"]))
    elif not want and open_item is not None:
        conn.execute(
            update(r)
            .where(r.c.id == open_item["id"])
            .values(
                status="resolved",
                resolution="deleted" if doc["deleted_at"] is not None else resolution,
                resolved_by=actor,
                resolved_at=now,
            )
        )


__all__ = [
    "KEEP",
    "error_code",
    "tx",
    "Change",
    "FileOps",
    "ForbiddenPath",
    "Fs",
    "GroupUndoResult",
    "Result",
    "UndoResult",
    "inbox_name",
    "is_suffix_of",
    "keep_review",
    "sha256_file",
    "suffixed",
    "utcnow",
]

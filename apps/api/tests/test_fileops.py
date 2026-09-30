"""C7 §10 obligations 2–14: guard, collisions, adoption, undo, delete, failures, recovery."""

import errno
import os
import threading
from contextlib import contextmanager
from pathlib import Path

import pytest
from sqlalchemy import insert, select, text

from mona.fileops import Change, FileOpError, ForbiddenPath, Fs, Roots, RootsError, SimulatedCrash
from mona.fileops.roots import inside, resolve_inside
from mona.fileops.state import T, group_state
from mona.ids import new_id
from tests.fileops_world import World

P = "Cabinet Marchand/Appels de paiement/2025/2026-02-27_OPCO_Contribution-OPCO_2025-A-118.pdf"
Q = "Cabinet Marchand/Assurances/UNIM/Prévoyance/2025/2025-11-03_UNIM_Prevoyance.pdf"
R = "Personnel/Impôts et taxes/2026/2026-05-12_OXYLEO_Elements-preparatoires.pdf"


@pytest.fixture
def w(migrated_engine, tmp_path) -> World:
    return World(migrated_engine, tmp_path / "data")


def snapshot(w: World, doc_id: str):
    f = T["file_ops"]
    with w.engine.connect() as conn:
        entries = list(conn.execute(select(f).where(f.c.document_id == doc_id)).mappings())
    return w.tree(), dict(w.doc(doc_id)), [dict(e) for e in entries]


# --- §3 guard (invariant 9) ---


@pytest.mark.parametrize(
    "rel", ["../x.pdf", "a/../../x.pdf", "/etc/passwd", "a\\b.pdf", "a/\x00.pdf", "a//b.pdf", "./x"]
)
def test_guard_rejects_bad_relative_paths(w, rel):
    with pytest.raises(ForbiddenPath):
        resolve_inside(w.roots.archive, rel, create=True)


def test_guard_rejects_a_symlinked_parent_even_pointing_inside(w):
    (w.roots.archive / "real").mkdir()
    os.symlink(w.roots.archive / "real", w.roots.archive / "link")
    with pytest.raises(ForbiddenPath, match="symlinked directory"):
        resolve_inside(w.roots.archive, "link/x.pdf", create=True)


def test_guard_rejects_a_symlinked_parent_pointing_outside(w, tmp_path):
    (tmp_path / "outside").mkdir()
    os.symlink(tmp_path / "outside", w.roots.archive / "out")
    with pytest.raises(ForbiddenPath):
        resolve_inside(w.roots.archive, "out/x.pdf", create=True)
    assert not (tmp_path / "outside" / "x.pdf").exists()


def test_guard_rejects_a_symlinked_target_file(w, tmp_path):
    (tmp_path / "secret").write_text("s")
    os.symlink(tmp_path / "secret", w.roots.archive / "x.pdf")
    with pytest.raises(ForbiddenPath, match="symlinked file"):
        resolve_inside(w.roots.archive, "x.pdf", taken_ok=True)


def test_guard_rejects_a_symlinked_source(w, tmp_path):
    doc = w.ingest()
    src = w.roots.inbox / f"{doc}.pdf"
    real = tmp_path / "elsewhere.pdf"
    os.replace(src, real)
    os.symlink(real, src)
    with pytest.raises(ForbiddenPath):
        w.file(doc, P)
    assert w.entries(doc, None) == []
    assert real.exists() and not (w.roots.archive / P).exists()


def test_guard_rejects_a_parent_on_another_device(w, monkeypatch):
    (w.roots.archive / "mnt").mkdir()
    real_lstat = os.lstat

    def fake(p, *a, **kw):
        st = real_lstat(p, *a, **kw)
        if str(p) == str(w.roots.archive / "mnt"):
            return os.stat_result((st.st_mode, st.st_ino, st.st_dev + 1, *tuple(st)[3:10]))
        return st

    monkeypatch.setattr("mona.fileops.roots.os.lstat", fake)
    with pytest.raises(ForbiddenPath, match="another filesystem"):
        resolve_inside(w.roots.archive, "mnt/x.pdf", create=True)


def test_guard_needs_the_separator_after_the_root(tmp_path):
    root = tmp_path / "archive"
    root.mkdir()
    (tmp_path / "archive-evil").mkdir()
    assert inside(root, root / "a")
    assert inside(root, root)
    assert not inside(root, tmp_path / "archive-evil")


def test_forbidden_target_writes_nothing(w):
    doc = w.ingest()
    with pytest.raises(ForbiddenPath):
        w.file(doc, "a/../../escape.pdf")
    assert w.entries(doc, None) == []
    assert (w.roots.inbox / f"{doc}.pdf").exists()


def test_single_filesystem_check_refuses_a_trash_on_another_device(w):
    real = os.lstat

    def fake(p):
        st = real(p)
        if Path(p) == w.roots.trash:
            return os.stat_result((st.st_mode, st.st_ino, st.st_dev + 1, *tuple(st)[3:10]))
        return st

    w.roots.check_single_filesystem()
    with pytest.raises(RootsError):
        w.roots.check_single_filesystem(lstat=fake)


# --- §4.2 A: stale, the Mona trash guard, no-op ---


def test_stale_expectation_aborts_with_nothing_written(w):
    doc = w.ingest()
    w.file(doc, P)
    before = snapshot(w, doc)
    c = w.change(doc, "move", "archive", Q)
    w.relocate(doc, R)
    moved = snapshot(w, doc)
    with pytest.raises(FileOpError) as err:
        w.ops.move(c)
    assert (err.value.code, err.value.hint) == ("conflict", "stale")
    assert snapshot(w, doc) == moved != before


def test_move_to_the_current_path_is_unchanged(w):
    doc = w.ingest()
    w.file(doc, P)
    n = len(w.entries(doc, None))
    assert w.relocate(doc, P).outcome == "unchanged"
    assert len(w.entries(doc, None)) == n


# --- §8.1 collisions (§10.4) ---


def test_three_documents_rendering_one_name_get_suffixes(w):
    docs = [w.ingest() for _ in range(3)]
    paths = [w.file(d, P).state["path"] for d in docs]
    stem = P.removesuffix(".pdf")
    assert paths == [P, f"{stem}-2.pdf", f"{stem}-3.pdf"]
    assert [w.doc(d)["current_path"] for d in docs] == paths
    w.check()


def test_a_directory_at_the_target_is_a_collision(w):
    (w.roots.archive / "d" / "x.pdf").mkdir(parents=True)
    doc = w.ingest()
    assert w.file(doc, "d/x.pdf").state["path"] == "d/x-2.pdf"


def test_concurrent_filing_to_one_name_keeps_both(w):
    docs = [w.ingest() for _ in range(2)]
    barrier = threading.Barrier(2)
    errors = []

    def run(d):
        try:
            barrier.wait()
            w.file(d, P)
        except Exception as e:  # pragma: no cover - reported below
            errors.append(e)

    threads = [threading.Thread(target=run, args=(d,)) for d in docs]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    paths = {w.doc(d)["current_path"] for d in docs}
    assert paths == {P, P.removesuffix(".pdf") + "-2.pdf"}
    w.check()


def test_eexist_at_link_takes_the_next_suffix(w):
    doc = w.ingest()
    real = Fs()

    class Racy(Fs):
        def link(self, src, dst):
            if dst.name == "x.pdf" and not dst.exists():
                dst.write_bytes(b"someone else")
            real.link(src, dst)

    w.ops.fs = Racy()
    r = w.file(doc, "d/x.pdf")
    assert r.state["path"] == "d/x-2.pdf" == w.entry(r.entry_id)["after"]["path"]
    w.check(archive_exact=False)


def test_collisions_exhaust_after_999(w):
    folder = w.roots.archive / "d"
    folder.mkdir()
    (folder / "x.pdf").write_bytes(b"0")
    for n in range(2, 1000):
        (folder / f"x-{n}.pdf").write_bytes(b"0")
    doc = w.ingest()
    with pytest.raises(FileOpError) as err:
        w.file(doc, "d/x.pdf")
    assert err.value.hint == "collision_exhausted"
    assert w.entries(doc, None) == []


# --- §8.3 identical bytes: adoption (§10.5) ---


def test_adoption_then_undo_restores_both_files(w):
    data = b"identical bytes"
    doc = w.ingest(data)
    target = w.roots.archive / "d" / "x.pdf"
    target.parent.mkdir()
    target.write_bytes(data)
    r = w.file(doc, "d/x.pdf")
    a = w.entry(r.entry_id)["after"]
    assert a["adopted"] is True and a["trash_copy"] == f"{doc}/x.pdf"
    assert w.doc(doc)["current_path"] == "d/x.pdf"
    assert (w.roots.trash / doc / "x.pdf").read_bytes() == data
    w.check()
    u = w.ops.undo(r.entry_id, actor="user", via="ui")
    assert u.state == "done"
    assert (w.roots.inbox / f"{doc}.pdf").read_bytes() == data
    assert target.read_bytes() == data
    assert not (w.roots.trash / doc / "x.pdf").exists()
    w.check(archive_exact=False)


def test_adoption_crashed_after_the_trash_move_is_completed_by_recovery(w):
    data = b"identical again"
    doc = w.ingest(data)
    target = w.roots.archive / "x.pdf"
    target.write_bytes(data)
    w.ops.crash_at = "after_b3"
    with pytest.raises(SimulatedCrash):
        w.file(doc, "x.pdf")
    w.ops.crash_at = None
    (pending,) = w.entries(doc, "pending")
    assert pending["after"]["trash_copy"] == f"{doc}/x.pdf"
    assert w.ops.recover_pending() == {pending["id"]: "done"}
    assert w.doc(doc)["current_path"] == "x.pdf"
    w.check()
    assert w.ops.undo(pending["id"], actor="user", via="ui").state == "done"
    assert (w.roots.inbox / f"{doc}.pdf").read_bytes() == data
    assert target.read_bytes() == data
    w.check(archive_exact=False)


# --- §5 undo and redo ---


def test_supersede_refuses_and_changes_nothing_then_unwinds(w):
    doc = w.ingest()
    f = w.file(doc, P).entry_id
    m = w.relocate(doc, Q).entry_id
    assert w.state(f) == "superseded"
    before = snapshot(w, doc)
    assert w.ops.undo(f, actor="user", via="ui").state == "superseded"
    assert snapshot(w, doc) == before
    assert w.ops.undo(m, actor="user", via="ui").state == "done"
    assert w.state(f) == "undoable"
    assert w.doc(doc)["current_path"] == P
    w.check()


def test_group_undo_runs_in_reverse_journal_order(w):
    doc = w.ingest()
    w.file(doc, P)
    g = new_id("grp")
    with w.engine.begin() as conn:
        conn.execute(insert(T["op_groups"]).values(id=g, kind="refile", actor="user", via="ui"))
    w.relocate(doc, Q, group_id=g, actor="user", via="ui")
    w.relocate(doc, R, group_id=g, actor="user", via="ui")
    r = w.ops.undo_group(g, actor="user", via="ui")
    assert len(r.undone) == 2 and not r.skipped
    assert w.doc(doc)["current_path"] == P
    w.check()


def test_undo_of_undo_is_redo_three_levels(w):
    doc = w.ingest()
    f = w.file(doc, P).entry_id
    target, seen = f, []
    for level, action in enumerate(["undo", "redo", "undo", "redo"], 1):
        r = w.ops.undo(target, actor="user", via="ui")
        assert r.state == "done"
        assert w.entry(r.entry_id)["action"] == action
        seen.append(w.doc(doc)["location"])
        assert w.state(f) == ("undone" if level % 2 else "undoable")
        assert w.state(target) == "undone" and w.state(r.entry_id) == "undoable"
        target = r.entry_id
    assert seen == ["inbox", "archive", "inbox", "archive"]
    assert w.doc(doc)["status"] == "filed"
    w.check()


def test_undoing_a_pipeline_filing_goes_back_to_review(w):
    doc = w.ingest()
    f = w.file(doc, P).entry_id
    w.ops.undo(f, actor="user", via="ui")
    d = w.doc(doc)
    assert (d["status"], list(d["reasons"]), d["location"]) == ("review", ["low"], "inbox")
    w.check()


def test_group_undo_then_redo_then_undo_again(w):
    docs = [w.ingest() for _ in range(3)]
    for d in docs:
        w.file(d, f"a/{d}.pdf")
    g = new_id("grp")
    with w.engine.begin() as conn:
        conn.execute(
            insert(T["op_groups"]).values(id=g, kind="rule_apply", actor="mona", via="chat")
        )
    for d in docs:
        w.relocate(d, f"b/{d}.pdf", group_id=g)
    tree_after_g = w.tree()
    u = w.ops.undo_group(g, actor="mona", via="chat")
    tree_after_undo = w.tree()
    assert all(w.doc(d)["current_path"] == f"a/{d}.pdf" for d in docs)
    redo = w.ops.undo_group(u.group_id, actor="mona", via="chat")
    assert w.tree() == tree_after_g
    with w.engine.connect() as conn:
        assert group_state(conn, g)[0] == "undoable"
        assert group_state(conn, u.group_id)[0] == "undone"
        assert group_state(conn, redo.group_id)[0] == "undoable"
        kinds = dict(conn.execute(select(T["op_groups"].c.id, T["op_groups"].c.kind)).all())
    assert (kinds[u.group_id], kinds[redo.group_id]) == ("undo", "redo")
    again = w.ops.undo_group(g, actor="mona", via="chat")
    assert {w.entry(x.entry_id)["undo_of"] for x in again.undone} == {
        x.entry_id for x in redo.undone
    }
    assert w.tree() == tree_after_undo
    w.check()


def test_group_undo_with_nothing_undoable_creates_no_group(w):
    doc = w.ingest()
    w.file(doc, P)
    g = new_id("grp")
    with w.engine.begin() as conn:
        conn.execute(insert(T["op_groups"]).values(id=g, kind="refile", actor="user", via="ui"))
    w.relocate(doc, Q, group_id=g, actor="user", via="ui")
    w.ops.undo_group(g, actor="user", via="ui")
    r = w.ops.undo_group(g, actor="user", via="ui")
    assert (r.group_id, r.state) == (None, "already_undone")


def test_failed_undo_does_not_block_a_retry(w):
    doc = w.ingest()
    f = w.file(doc, P).entry_id

    class Deny(Fs):
        def link(self, src, dst):
            raise PermissionError(errno.EACCES, "denied")

    w.ops.fs = Deny()
    with pytest.raises(FileOpError) as err:
        w.ops.undo(f, actor="user", via="ui")
    assert err.value.hint == "EACCES"
    assert [e["fs_state"] for e in w.entries(doc, None)] == ["done", "failed"]
    w.ops.fs = Fs()
    assert w.ops.undo(f, actor="user", via="ui").state == "done"
    w.check()


# --- §6 badge (§10.9) ---


def test_badge_lifecycle(w):
    from mona.fileops import badge_until

    doc = w.ingest()
    w.file(doc, P)
    filed_at = w.doc(doc)["filed_at"]
    assert badge_until(w.doc(doc), 24, w.clock()) is not None
    w.clock.advance(hours=25)
    assert badge_until(w.doc(doc), 24, w.clock()) is None
    w.clock.advance(hours=-24)
    m = w.relocate(doc, Q, actor="user", via="ui").entry_id
    assert badge_until(w.doc(doc), 24, w.clock()) is None
    w.ops.undo(m, actor="user", via="ui")
    d = w.doc(doc)
    assert (d["filed_by"], d["filed_at"]) == ("mona", filed_at)
    assert badge_until(d, 24, w.clock()) == filed_at + __import__("datetime").timedelta(hours=24)
    w.check()


# --- §7 delete (§10.10) ---


def test_user_delete_and_restore(w):
    doc = w.ingest(status="review")
    r = w.ops.delete(doc, actor="user", via="ui")
    d = w.doc(doc)
    assert (d["location"], d["current_path"], d["status"]) == (
        "trash",
        f"{doc}/{doc}.pdf",
        "review",
    )
    assert d["deleted_at"] is not None
    items = T["review_items"]
    with w.engine.connect() as conn:
        res = conn.execute(select(items.c.resolution).where(items.c.document_id == doc)).scalars()
        assert list(res) == ["deleted"]
    w.check()
    assert w.ops.undo(r.entry_id, actor="user", via="ui").state == "done"
    d = w.doc(doc)
    assert (d["location"], d["deleted_at"]) == ("inbox", None)
    w.check()


def test_mona_can_never_delete(w):
    doc = w.ingest()
    w.file(doc, P)
    with pytest.raises(FileOpError) as err:
        w.ops.delete(doc, actor="mona", via="chat")
    assert err.value.code == "not_allowed"
    d = w.ops.delete(doc, actor="user", via="ui")
    restore = w.ops.undo(d.entry_id, actor="user", via="ui")
    before = snapshot(w, doc)
    assert w.ops.undo(restore.entry_id, actor="mona", via="chat").state == "not_allowed"
    assert snapshot(w, doc) == before
    g = new_id("grp")
    with w.engine.begin() as conn:
        conn.execute(insert(T["op_groups"]).values(id=g, kind="refile", actor="user", via="ui"))
        conn.execute(
            T["file_ops"].update().where(T["file_ops"].c.id == restore.entry_id).values(group_id=g)
        )
    r = w.ops.undo_group(g, actor="mona", via="telegram")
    assert [s.state for s in r.skipped] == ["not_allowed"] and not r.undone
    assert snapshot(w, doc)[:2] == before[:2]
    w.check()


# --- §4.2 failures (§10.12) ---


def test_eacces_at_link_fails_the_entry_and_releases_the_lock(w):
    doc = w.ingest()

    class Deny(Fs):
        def link(self, src, dst):
            raise PermissionError(errno.EACCES, "denied")

    w.ops.fs = Deny()
    with pytest.raises(FileOpError) as err:
        w.file(doc, P)
    assert (err.value.code, err.value.hint) == ("conflict", "EACCES")
    assert [e["fs_state"] for e in w.entries(doc, None)] == ["failed"]
    assert (w.roots.inbox / f"{doc}.pdf").exists() and not (w.roots.archive / P).exists()
    with w.engine.connect() as conn:
        got = conn.execute(
            text("SELECT pg_try_advisory_lock(hashtextextended(:k, 0))"), {"k": doc}
        ).scalar()
        conn.execute(text("SELECT pg_advisory_unlock(hashtextextended(:k, 0))"), {"k": doc})
    assert got is True
    w.check()


def test_enoent_at_link_once_is_retried(w):
    doc = w.ingest()
    calls = []

    class Flaky(Fs):
        def link(self, src, dst):
            calls.append(dst)
            if len(calls) == 1:
                raise FileNotFoundError(errno.ENOENT, "gone")
            super().link(src, dst)

    w.ops.fs = Flaky()
    r = w.file(doc, P)
    assert r.outcome == "moved" and len(calls) == 2
    w.check()


def test_enoent_twice_fails(w):
    doc = w.ingest()

    class Gone(Fs):
        def link(self, src, dst):
            raise FileNotFoundError(errno.ENOENT, "gone")

    w.ops.fs = Gone()
    with pytest.raises(FileOpError) as err:
        w.file(doc, P)
    assert err.value.hint == "ENOENT"
    assert [e["fs_state"] for e in w.entries(doc, None)] == ["failed"]
    w.check()


# --- §4.3 recovery and crash injection (§10.2, §10.13) ---


@pytest.mark.parametrize(
    ("point", "applied"),
    [("after_a", False), ("after_b1", True), ("after_b3", True), ("in_c", True)],
)
def test_crash_then_recovery(w, point, applied):
    doc = w.ingest()
    w.ops.crash_at = point
    with pytest.raises(SimulatedCrash):
        w.file(doc, P)
    w.ops.crash_at = None
    (pending,) = w.entries(doc, "pending")
    out = w.ops.recover_pending()
    assert out == {pending["id"]: "done" if applied else "failed"}
    d = w.doc(doc)
    assert d["location"] == ("archive" if applied else "inbox")
    w.check()


@pytest.mark.parametrize(
    ("point", "applied"),
    [("after_a", False), ("after_b1", True), ("after_b3", True), ("in_c", True)],
)
def test_crash_then_another_operation_recovers_first(w, point, applied):
    doc = w.ingest()
    w.ops.crash_at = point
    with pytest.raises(SimulatedCrash):
        w.file(doc, P)
    w.ops.crash_at = None
    stale = w.change(doc, "file", "archive", Q, actor="user", via="ui")
    if applied:
        with pytest.raises(FileOpError, match="moved meanwhile"):
            w.ops.move(stale)
        assert w.doc(doc)["current_path"] == P
        w.relocate(doc, Q)
    else:
        assert w.ops.move(stale).outcome == "moved"
    assert w.entries(doc, "pending") == []
    assert w.doc(doc)["current_path"] == Q
    assert w.ops.recover_pending() == {}
    w.check()


def test_stale_pending_entry_then_retry_then_recovery(w):
    doc = w.ingest()

    class Deny(Fs):
        def link(self, src, dst):
            raise PermissionError(errno.EACCES, "denied")

    w.ops.fs = Deny()
    w.ops._cleanup = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("cleanup down"))
    with pytest.raises(RuntimeError):
        w.file(doc, P)
    assert [e["fs_state"] for e in w.entries(doc, None)] == ["pending"]
    del w.ops._cleanup
    w.ops.fs = Fs()
    r = w.file(doc, P)
    cls_before = w.doc(doc)["classification_id"]
    assert w.ops.recover_pending() == {}
    assert [e["fs_state"] for e in w.entries(doc, None)] == ["failed", "done"]
    assert len(w.entries(doc)) == 1 and w.entries(doc)[0]["id"] == r.entry_id
    assert w.doc(doc)["classification_id"] == cls_before
    w.check()


def _pending(w: World, doc: str, before: dict, after: dict) -> int:
    f = T["file_ops"]
    with w.engine.begin() as conn:
        return conn.execute(
            insert(f)
            .values(actor="mona", via="chat", action="move", document_id=doc,
                    sha256=w.doc(doc)["sha256"], before=before, after=after,
                    fs_state="pending", undoable=True)
            .returning(f.c.id)
        ).scalar_one()  # fmt: skip


def _filed(w: World):
    doc = w.ingest()
    w.file(doc, P)
    d = w.doc(doc)
    before = {"location": "archive", "path": P, "status": "filed", "reasons": [],
              "classification_id": None, "rule_id": None, "filed_by": d["filed_by"],
              "filed_at": d["filed_at"].isoformat()}  # fmt: skip
    return doc, before, {**before, "path": Q, "filed_by": "user"}


def test_recovery_row_src_only_fails(w):
    doc, b, a = _filed(w)
    eid = _pending(w, doc, b, a)
    assert w.ops.recover_pending() == {eid: "failed"}
    assert w.doc(doc)["current_path"] == P
    w.check()


def test_recovery_row_linked_not_unlinked_completes(w):
    doc, b, a = _filed(w)
    (w.roots.archive / Q).parent.mkdir(parents=True, exist_ok=True)
    os.link(w.roots.archive / P, w.roots.archive / Q)
    eid = _pending(w, doc, b, a)
    assert w.ops.recover_pending() == {eid: "done"}
    assert w.doc(doc)["current_path"] == Q and not (w.roots.archive / P).exists()
    w.check()


def test_recovery_row_name_taken_by_something_else_fails(w):
    doc, b, a = _filed(w)
    (w.roots.archive / Q).parent.mkdir(parents=True, exist_ok=True)
    (w.roots.archive / Q).write_bytes(b"other")
    eid = _pending(w, doc, b, a)
    assert w.ops.recover_pending() == {eid: "failed"}
    assert (w.roots.archive / Q).read_bytes() == b"other"
    w.check(archive_exact=False)


def test_recovery_row_moved_completes(w):
    doc, b, a = _filed(w)
    (w.roots.archive / Q).parent.mkdir(parents=True, exist_ok=True)
    os.rename(w.roots.archive / P, w.roots.archive / Q)
    eid = _pending(w, doc, b, a)
    assert w.ops.recover_pending() == {eid: "done"}
    assert w.doc(doc)["current_path"] == Q
    w.check()


def test_recovery_row_both_missing_marks_missing_file(w):
    doc, b, a = _filed(w)
    os.unlink(w.roots.archive / P)
    eid = _pending(w, doc, b, a)
    assert w.ops.recover_pending() == {eid: "failed"}
    assert w.doc(doc)["pipeline_error"] == "missing_file"


def test_recovery_skips_an_entry_whose_document_moved(w):
    doc, b, a = _filed(w)
    (w.roots.archive / Q).parent.mkdir(parents=True, exist_ok=True)
    (w.roots.archive / Q).write_bytes((w.roots.archive / P).read_bytes())
    eid = _pending(w, doc, {**b, "path": "elsewhere.pdf"}, a)
    tree = w.tree()
    assert w.ops.recover_pending() == {eid: "failed"}
    assert w.tree() == tree
    d = w.doc(doc)
    assert (d["current_path"], d["pipeline_error"]) == (P, None)


def test_recovery_rechecks_the_entry_under_the_lock(w):
    doc = w.ingest()
    w.ops.crash_at = "after_b1"
    with pytest.raises(SimulatedCrash):
        w.file(doc, P)
    w.ops.crash_at = None
    (pending,) = w.entries(doc, "pending")
    real = w.ops.locked
    raced = []

    @contextmanager
    def racing(document_id):
        if not raced:
            raced.append(document_id)
            w.ops.move(Change(doc, "move", "archive", Q, "user", "ui", ("archive", P), "filed", ()))
        with real(document_id) as conn:
            yield conn

    w.ops.locked = racing
    assert w.ops.recover_pending() == {pending["id"]: "skipped"}
    assert [e["fs_state"] for e in w.entries(doc, None)] == ["done", "done"]
    assert w.doc(doc)["current_path"] == Q
    w.check()


def test_recovery_leaves_young_entries_to_their_operation(w):
    doc, b, a = _filed(w)
    eid = _pending(w, doc, b, a)
    from datetime import timedelta

    with w.engine.begin() as conn:
        f = T["file_ops"]
        conn.execute(f.update().where(f.c.id == eid).values(at=w.clock()))
    assert w.ops.recover_pending(timedelta(seconds=30)) == {}
    w.clock.advance(seconds=31)
    assert w.ops.recover_pending(timedelta(seconds=30)) == {eid: "failed"}


def test_empty_source_folders_are_tidied_but_never_the_root(w):
    doc = w.ingest()
    w.file(doc, "a/b/c/x.pdf")
    w.relocate(doc, "z/x.pdf")
    assert not (w.roots.archive / "a").exists()
    w.relocate(doc, "x.pdf")
    assert w.roots.archive.is_dir() and not (w.roots.archive / "z").exists()


def test_roots_resolve_once_with_realpath(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    os.symlink(real, tmp_path / "data")
    roots = Roots.at(tmp_path / "data")
    assert roots.archive == real / "archive"

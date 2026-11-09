"""A37: the per-sha256 lock between intake and the undo of a delete, and the A24 fallback."""

import hashlib
import secrets
import threading
from typing import Any

import pytest
from sqlalchemy import select

from mona.fileops import FileOps, inbox_name, sha256_file
from mona.ids import new_id
from mona.pipeline import intake
from mona.pipeline.intake import Upload, ingest_files
from mona.services import delete_document, undo
from mona.services.errors import ServiceError
from mona.services.registry import T
from tests.pipeline_world import Pipeline, mini_pdf

WAIT = 1.0
RUNS = 20


@pytest.fixture
def p(l1m2_demo_engine, tmp_path) -> Pipeline:
    return Pipeline(l1m2_demo_engine, tmp_path / "data")


def deleted_document(p: Pipeline) -> tuple[bytes, str, int]:
    data = mini_pdf([f"A fictional letter {secrets.token_hex(8)}."])
    doc = ingest_files(p.ctx, [Upload(data, "letter.pdf")]).items[0].document_id
    assert doc is not None
    return data, doc, delete_document(p.ctx, doc, actor="user", via="ui").id


def rows_for(p: Pipeline, sha: str) -> list[Any]:
    d = T["documents"]
    with p.engine.connect() as conn:
        return conn.execute(select(d).where(d.c.sha256 == sha)).mappings().all()


def unsettled(p: Pipeline, doc: str) -> list[Any]:
    f = T["file_ops"]
    with p.engine.connect() as conn:
        q = select(f.c.id).where(f.c.document_id == doc, f.c.fs_state.in_(("pending", "failed")))
        return conn.execute(q).all()


def files_in_place(p: Pipeline, sha: str) -> None:
    for r in rows_for(p, sha):
        assert sha256_file(p.ctx.ops.roots.root(r["location"]) / r["current_path"]) == sha


def test_an_upload_racing_an_undo_of_delete_has_one_winner_and_no_500(p, monkeypatch):
    gate: dict[str, Any] = {}

    def then_wait(fn, mark=None):
        def wrapped(*args, **kwargs):
            out = fn(*args, **kwargs)
            if mark in gate:
                gate[mark].set()
            if barrier := gate.get("barrier"):
                try:
                    barrier.wait(WAIT)
                except threading.BrokenBarrierError:
                    pass
            return out

        return wrapped

    monkeypatch.setattr(intake, "_twin", then_wait(intake._twin))
    monkeypatch.setattr(
        FileOps, "_restore_guard", then_wait(FileOps._restore_guard, "restore_checked")
    )
    seen = []
    for run in range(RUNS):
        data, doc, entry = deleted_document(p)
        gate["barrier"] = threading.Barrier(2)
        lead = threading.Event() if run % 2 else None
        if lead is not None:
            gate["restore_checked"] = lead
        out: dict[str, Any] = {}

        def upload(data=data, out=out, lead=lead):
            if lead is not None:
                lead.wait(WAIT * 5)
            try:
                out["intake"] = ingest_files(p.ctx, [Upload(data, "again.pdf")]).items[0]
            except BaseException as e:  # noqa: B036
                out["intake"] = e

        def restore(entry=entry, out=out):
            try:
                out["undo"] = undo(p.ctx, actor="user", via="ui", journal_id=entry)
            except BaseException as e:  # noqa: B036
                out["undo"] = e

        threads = [threading.Thread(target=upload), threading.Thread(target=restore)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)
        gate.clear()
        item, done = out["intake"], out["undo"]
        assert not isinstance(item, BaseException), repr(item)
        if isinstance(done, ServiceError):
            assert (done.code, done.hint) == ("conflict", "duplicate")
            assert item.outcome == "accepted"
            winner = item.document_id
        else:
            assert not isinstance(done, BaseException), repr(done)
            assert len(done.undone) == 1
            assert (item.outcome, item.document_id) == ("duplicate", doc)
            winner = doc
        sha = item.sha256
        assert [r["id"] for r in rows_for(p, sha) if r["deleted_at"] is None] == [winner]
        assert unsettled(p, doc) == []
        files_in_place(p, sha)
        seen.append("upload" if winner != doc else "undo")
    print(f"winners over {RUNS} runs: upload {seen.count('upload')}, undo {seen.count('undo')}")


def test_a_twin_that_reaches_the_a24_index_at_commit_is_a_duplicate_conflict(p, monkeypatch):
    """A twin written without the lock between the restore's intent and its commit."""
    data, doc, entry = deleted_document(p)
    twin: dict[str, str] = {}
    guard = FileOps._restore_guard

    def guard_then_twin(self, conn, d):
        guard(self, conn, d)
        twin["id"] = insert_twin(p, data, d["batch_id"])

    monkeypatch.setattr(FileOps, "_restore_guard", guard_then_twin)
    with pytest.raises(ServiceError) as err:
        undo(p.ctx, actor="user", via="ui", journal_id=entry)
    assert (err.value.code, err.value.hint) == ("conflict", "duplicate")
    sha = hashlib.sha256(data).hexdigest()
    rows = {r["id"]: r for r in rows_for(p, sha)}
    assert rows[doc]["location"] == "trash" and rows[doc]["deleted_at"] is not None
    assert rows[twin["id"]]["deleted_at"] is None
    f = T["file_ops"]
    with p.engine.connect() as conn:
        states = conn.execute(
            select(f.c.fs_state).where(f.c.document_id == doc).order_by(f.c.id)
        ).scalars()
        assert list(states) == ["done", "failed"]
    files_in_place(p, sha)


def insert_twin(p: Pipeline, data: bytes, batch_id: str) -> str:
    d = T["documents"]
    doc = new_id("doc")
    rel = inbox_name(doc, "application/pdf")
    (p.ctx.ops.roots.inbox / rel).write_bytes(data)
    now = p.clock()
    with p.engine.begin() as conn:
        conn.execute(
            d.insert().values(
                id=doc, sha256=hashlib.sha256(data).hexdigest(), original_name="twin.pdf",
                mime_type="application/pdf", size_bytes=len(data), source="drop", batch_id=batch_id,
                arrived_at=now, location="inbox", current_path=rel, status="processing",
                pipeline_stage="queued", created_at=now, updated_at=now,
            )
        )  # fmt: skip
    return doc

"""C6 §3.1: the hooks L1 calls after its pipeline commits; A10 (no deadline for a visitor)."""

import errno
from datetime import timedelta
from types import SimpleNamespace

import pytest

from mona.app import pipeline_startup
from mona.fileops import Fs, SimulatedCrash
from mona.interviews import hooks as c6
from mona.pipeline import runtime, stages
from mona.pipeline.hooks import interview_hooks
from mona.pipeline.intake import ingest_files
from mona.pipeline.model import TransportError
from tests.pipeline_world import RECORDED, SYNTHETIC, FakeModel, Pipeline


@pytest.fixture
def calls(monkeypatch):
    seen: list[tuple[str, str]] = []
    monkeypatch.setattr(c6, "on_batch_done", lambda b: seen.append(("done", b)))
    monkeypatch.setattr(c6, "on_document_settled", lambda b: seen.append(("settled", b)))
    return seen


def wired(engine, tmp_path, **kw) -> Pipeline:
    p = Pipeline(engine, tmp_path / "data", **kw)
    for name, hook in interview_hooks().items():
        setattr(p.ctx, name, hook)
    return p


def ids(out) -> list[str]:
    return [i.document_id for i in out.items]


def test_each_settle_then_the_batch_end_reach_the_c6_hooks(l1m2_demo_engine, tmp_path, calls):
    p = wired(l1m2_demo_engine, tmp_path)
    out = p.drop_synthetic(["syn-sie-letter", "syn-unreadable", "syn-agipi-per"])
    filed, unreadable, review = ids(out)
    p.cache_model(p.row(review)["sha256"], {**RECORDED["outputs"]["syn-agipi-per"], "entity": None})
    p.drain()
    assert [p.row(d)["status"] for d in (filed, unreadable, review)] == [
        "filed", "unreadable", "review",
    ]  # fmt: skip
    assert calls == [("settled", out.batch_id)] * 3 + [("done", out.batch_id)]


def test_a_failed_classification_settles(l1m2_demo_engine, tmp_path, calls):
    model = FakeModel({SYNTHETIC["syn-sie-letter"]["file"]: TransportError("ModelHTTPError")})
    p = wired(l1m2_demo_engine, tmp_path, model=model)
    out = p.drop_synthetic(["syn-sie-letter"], outputs=False)
    p.drain()
    assert p.row(ids(out)[0])["pipeline_stage"] == "failed"
    assert calls == [("settled", out.batch_id), ("done", out.batch_id)]


class _NoLink(Fs):
    def link(self, src, dst):
        raise OSError(errno.EACCES, "EACCES")


def test_a_failed_filing_settles(l1m2_demo_engine, tmp_path, calls):
    p = wired(l1m2_demo_engine, tmp_path, fs=_NoLink())
    out = p.drop_synthetic(["syn-oxyleo-prep"])
    p.drain()
    assert p.row(ids(out)[0])["pipeline_error"] == "EACCES"
    assert calls == [("settled", out.batch_id), ("done", out.batch_id)]


def test_a_filing_finished_by_recovery_settles_once(l1m2_demo_engine, tmp_path, calls):
    p = wired(l1m2_demo_engine, tmp_path)
    out = p.drop_synthetic(["syn-oxyleo-prep"])
    p.ctx.ops.crash_at = "in_c"
    with pytest.raises(SimulatedCrash):
        p.drain()
    assert calls == []
    p.ctx.ops.crash_at = None
    p.clock.advance(minutes=1)
    assert list(stages.recover(p.ctx, timedelta(seconds=30)).values()) == ["done"]
    assert p.row(ids(out)[0])["status"] == "filed"
    assert calls == [("settled", out.batch_id), ("done", out.batch_id)]


def test_a_batch_done_at_creation_only_ends(l1m2_demo_engine, tmp_path, calls):
    p = wired(l1m2_demo_engine, tmp_path)
    out = ingest_files(p.ctx, [])
    assert out.batch_done and calls == [("done", out.batch_id)]


def test_a_failing_hook_never_fails_the_job(l1m2_demo_engine, tmp_path, monkeypatch):
    def boom(batch_id):
        raise RuntimeError("queue down")

    monkeypatch.setattr(c6, "on_batch_done", boom)
    monkeypatch.setattr(c6, "on_document_settled", boom)
    p = wired(l1m2_demo_engine, tmp_path)
    doc = ids(p.drop_synthetic(["syn-oxyleo-prep"]))[0]
    p.drain()
    assert p.row(doc)["status"] == "filed"
    assert [x[2] for x in p.ran if x[0] == "file_document"] == ["filed"]


def test_the_api_and_worker_contexts_call_the_c6_hooks(calls):
    runtime.get_context.cache_clear()
    try:
        ctx = runtime.get_context()
        ctx.on_document_settled("bat_worker")
        ctx.on_batch_done("bat_worker")
    finally:
        runtime.get_context.cache_clear()
    app = SimpleNamespace(state=SimpleNamespace())
    pipeline_startup(app)
    app.state.pipeline.on_batch_done("bat_api")
    assert calls == [("settled", "bat_worker"), ("done", "bat_worker"), ("done", "bat_api")]


def test_a_visitor_document_gets_no_extracted_deadline(l1m2_demo_engine, tmp_path):
    p = Pipeline(l1m2_demo_engine, tmp_path / "data")
    doc = ids(p.drop_synthetic(["syn-agipi-per"], visitor=True))[0]
    p.drain()
    r = p.row(doc)
    assert (r["status"], str(r["due_date"])) == ("filed", "2026-11-01")
    assert r["current_path"].startswith("Visitors/")
    assert p.rows("deadlines") == []
    assert [e for e in p.rows("file_ops") if e["action"] == "deadline.add"] == []

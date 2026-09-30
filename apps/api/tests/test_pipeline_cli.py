"""Wiring: `mona pipeline run`, the api startup (make_context + recovery), `mona worker`."""

import hashlib
import importlib
import json

import pytest
from typer.testing import CliRunner

from mona import cli
from mona.db import get_engine, get_sessionmaker, get_sync_engine, get_sync_sessionmaker
from mona.pipeline import cache, runtime
from mona.pipeline.schema import PROMPT_VERSION
from mona.settings import get_settings
from tests.pg import scratch_db, sqlalchemy_url_for
from tests.pipeline_world import RECORDED, SYNTHETIC, content_for


def _clear() -> None:
    for f in (get_settings, get_engine, get_sessionmaker, get_sync_engine, get_sync_sessionmaker,
              runtime.get_context, runtime.get_model):  # fmt: skip
        f.cache_clear()


@pytest.fixture
def stack(l1m2_demo_template, tmp_path, monkeypatch):
    """Settings, the sync engine and the jobs app pointed at a scratch copy of the demo seed."""
    import mona.jobs

    with scratch_db(template=l1m2_demo_template) as db:
        monkeypatch.setenv("DATABASE_URL", sqlalchemy_url_for(db))
        monkeypatch.setenv("MONA_DATA_DIR", str(tmp_path / "data"))
        monkeypatch.setenv("MONA_LLM_MODEL", RECORDED["model"])
        _clear()
        importlib.reload(mona.jobs)
        try:
            yield tmp_path / "data"
        finally:
            get_sync_engine().dispose()
            monkeypatch.undo()
            _clear()
            importlib.reload(mona.jobs)


def test_pipeline_run_inline_processes_a_batch(stack, tmp_path):
    files = []
    for doc_id in ("syn-test-opco", "syn-unreadable"):
        data = content_for(doc_id)
        sha = hashlib.sha256(data).hexdigest()
        s = SYNTHETIC[doc_id]
        cache.write_pages(stack / "textcache", cache.Pages(sha, s["method"], tuple(s["pages"])))
        if doc_id in RECORDED["outputs"]:
            cache.write_model(stack / "textcache", sha, PROMPT_VERSION, RECORDED["model"],
                              RECORDED["outputs"][doc_id])  # fmt: skip
        f = tmp_path / s["file"]
        f.write_bytes(data)
        files.append(str(f))
    report = tmp_path / "report.json"
    result = CliRunner().invoke(
        cli.app, ["pipeline", "run", "--inline", "--timeout", "60", "--report", str(report), *files]
    )
    assert result.exit_code == 0, result.output
    rows = json.loads(report.read_text())
    assert [(r["outcome"], r["status"], r["stage"]) for r in rows] == [
        ("accepted", "filed", "done"), ("accepted", "unreadable", "done"),
    ]  # fmt: skip
    assert rows[0]["path"].startswith("Cabinet Orthodontie/Appels de paiement/2026/")
    assert rows[0]["from_cache"] is True and set(rows[0]["stages"]) >= {
        "extract_text", "classify_document", "file_document",
    }  # fmt: skip
    assert "filed" in result.output and "unreadable" in result.output


async def test_api_startup_builds_the_context_and_recovers(app_db, tmp_path, monkeypatch):
    from mona.app import create_app

    calls = []
    monkeypatch.setenv("MONA_DATA_DIR", str(tmp_path / "api-data"))
    get_settings.cache_clear()
    monkeypatch.setattr("mona.pipeline.stages.recover", lambda ctx, older: calls.append(older))
    app = create_app()
    async with app.router.lifespan_context(app):
        assert app.state.pipeline.data_dir == (tmp_path / "api-data").resolve()
        assert (tmp_path / "api-data" / "inbox").is_dir()
    assert [c.total_seconds() for c in calls] == [0]
    get_settings.cache_clear()


def test_worker_runs_startup_before_the_worker(monkeypatch):
    import mona.jobs

    order = []
    monkeypatch.setattr(runtime, "get_context", lambda: order.append("context"))
    monkeypatch.setattr(runtime, "startup", lambda: order.append("recover"))
    monkeypatch.setattr(mona.jobs.app, "run_worker", lambda **kw: order.append(kw))
    assert (
        CliRunner().invoke(cli.app, ["worker", "--queues", "cpu", "--concurrency", "3"]).exit_code
        == 0
    )
    assert CliRunner().invoke(cli.app, ["worker", "--queues", "llm"]).exit_code == 0
    assert order == ["context", "recover", {"queues": ["cpu"], "concurrency": 3},
                     "context", {"queues": ["llm"], "concurrency": 1}]  # fmt: skip

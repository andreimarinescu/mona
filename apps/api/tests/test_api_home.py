"""C2 §3 shell and Home, §15 settings and system status, §1.5 ETags."""

from datetime import UTC, date, datetime, timedelta

import httpx
import psycopg
import pytest

from mona import clock
from mona.api import home, system
from mona.app import create_app
from mona.settings import Settings, get_settings
from tests import rows
from tests.api_client import api_client


@pytest.fixture
def app(l2_world, monkeypatch):
    monkeypatch.setattr(home, "_hermes", {"at": float("-inf"), "health": None})
    monkeypatch.setattr(system, "_status", {"at": float("-inf"), "body": None})
    return create_app()


def sql(stmt: str, params: tuple = ()) -> list:
    with psycopg.connect(get_settings().libpq_url) as conn:
        cur = conn.execute(stmt, params)
        return cur.fetchall() if cur.description else []


def mock_http(monkeypatch, module, handler) -> list[str]:
    """Routes httpx clients made without a transport to `handler`; returns the URLs requested."""
    seen: list[str] = []
    real = httpx.AsyncClient

    def wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return handler(request)

    def client(*args, **kw):
        if "transport" in kw:
            return real(*args, **kw)
        return real(*args, transport=httpx.MockTransport(wrapped), **kw)

    monkeypatch.setattr(module.httpx, "AsyncClient", client)
    return seen


def job(queue: str, status: str) -> None:
    sql(
        "INSERT INTO procrastinate_jobs (queue_name, task_name, status, args)"
        " VALUES (%s, 'x', %s, '{}')",
        (queue, status),
    )


# --- §3.1 shell ---


async def test_shell_counts_review_processing_and_queues(l2_world, app):
    w = l2_world
    w.doc()
    gone = w.doc()
    w.ctx.ops.delete(gone, actor="user", via="ui")
    rows.document("Still reading", status="processing", entity=None, category=None)
    job("llm", "todo"), job("llm", "doing"), job("cpu", "todo"), job("cpu", "succeeded")
    try:
        async with api_client(app) as cl:
            body = (await cl.get("/api/shell")).json()
    finally:
        sql("DELETE FROM procrastinate_jobs")
    assert body == {
        "reviewCount": 1, "processingCount": 1, "queue": {"llm": 2, "cpu": 1}, "mona": "offline",
    }  # fmt: skip


async def test_shell_says_online_when_hermes_answers_and_caches_it(l2_world, app, monkeypatch):
    seen = mock_http(monkeypatch, home, lambda r: httpx.Response(200, json={"version": "0.21.5"}))
    async with api_client(app) as cl:
        first = (await cl.get("/api/shell")).json()
        second = (await cl.get("/api/shell")).json()
    assert first["mona"] == second["mona"] == "online"
    assert seen == ["http://hermes:8642/health"]


async def test_polled_endpoints_answer_304_to_their_etag(l2_world, app):
    w = l2_world
    doc = w.doc()
    async with api_client(app) as cl:
        shell = await cl.get("/api/shell")
        same = await cl.get("/api/shell", headers={"If-None-Match": shell.headers["etag"]})
        w.doc()
        changed = await cl.get("/api/shell", headers={"If-None-Match": shell.headers["etag"]})
        detail = await cl.get(f"/api/documents/{doc}")
        cached = await cl.get(
            f"/api/documents/{doc}", headers={"If-None-Match": detail.headers["etag"]}
        )
    assert shell.headers["etag"].startswith('W/"')
    assert same.status_code == 304 and same.content == b""
    assert changed.status_code == 200 and changed.json()["reviewCount"] == 2
    assert detail.json()["id"] == doc and cached.status_code == 304


# --- §3.2 Home ---


async def test_home_brief_review_due_activity_and_ingestion(l2_world, app):
    w = l2_world
    today = clock.paris_today()
    now = datetime.now(UTC)
    rows.document("Filed today", filed_at=now)
    rows.document("Filed last week", filed_at=now - timedelta(days=7))
    reviews = [w.doc(arrived_at=now - timedelta(hours=10 - i)) for i in range(4)]
    soon = [rows.deadline(f"Due {i}", today + timedelta(days=i), amount=10.0) for i in range(4)]
    visitor_batch = w.new_batch(visitor=True)
    visitor_doc = rows.document("A visitor's bill", entity="visitors", batch_id=visitor_batch)
    rows.deadline("Visitor bill", today, entity="visitors", document_id=visitor_doc)
    w.ctx.ops.delete(reviews[3], actor="user", via="ui")
    async with api_client(app) as cl:
        body = (await cl.get("/api/home")).json()
        scoped = (
            await cl.get("/api/home", params={"entityId": w.ids("entities")["studio"]})
        ).json()
        bad = await cl.get("/api/home", params={"entityId": "doc_" + "0" * 26})
    facts = body["facts"]
    assert facts["filed"]["count"] == 1
    assert facts["filed"]["byEntity"][0]["entityId"] == w.ids("entities")["cabinet"]
    assert facts["needsReview"] == {"count": 3, "byReason": {"low": 3}}
    assert [d["label"] for d in facts["dueSoon"]] == ["Due 0", "Due 1", "Due 2", "Due 3"]
    assert body["review"]["total"] == 3
    assert [d["id"] for d in body["review"]["items"]] == reviews[:3]
    assert body["due"]["total"] == 4 and [d["id"] for d in body["due"]["items"]] == soon[:3]
    assert body["journalEntryCount"] == 1
    assert [i["entry"]["action"] for i in body["activity"]["items"]] == ["delete"]
    assert reviews[3] in body["activity"]["documents"]
    days = body["ingestion"]["days"]
    assert len(days) == 14 and days[-1]["date"] == today.isoformat()
    assert days[-1]["count"] >= 3 and body["ingestion"]["lastBatch"]["id"] == visitor_batch
    assert scoped["facts"]["filed"]["count"] == 0 and scoped["due"]["total"] == 0
    assert bad.status_code == 400 and bad.json()["error"]["field"] == "entityId"


async def test_home_since_widens_the_window(l2_world, app):
    rows.document("Filed last week", filed_at=datetime.now(UTC) - timedelta(days=6))
    since = (datetime.now(UTC) - timedelta(days=7)).isoformat()
    async with api_client(app) as cl:
        body = (await cl.get("/api/home", params={"since": since})).json()
    assert body["facts"]["filed"]["count"] == 1 and body["facts"]["since"].startswith(since[:16])


# --- §15.1 settings ---


async def test_settings_read_and_patch(l2_world, app):
    async with api_client(app) as cl:
        view = (await cl.get("/api/settings")).json()
        res = await cl.patch(
            "/api/settings",
            json={"autoLockMinutes": 120, "debriefEarlyMin": 7, "profileName": " Claire "},
        )
    assert set(view) == {
        "profileName", "locale", "autoLockMinutes", "practiceName", "filingLanguage",
        "confidenceHigh", "confidenceLow", "badgeHours", "debriefQueueThreshold",
        "debriefEarlyMin",
    }  # fmt: skip
    body = res.json()
    assert res.status_code == 200 and body["autoLockMinutes"] == 120
    assert body["debriefEarlyMin"] == 7 and body["profileName"] == "Claire"
    assert sql("SELECT auto_lock_minutes, name FROM profile") == [(120, "Claire")]
    assert sql("SELECT debrief_early_min FROM settings") == [(7,)]
    assert sql("SELECT count(*) FROM file_ops") == [(0,)]


@pytest.mark.parametrize(
    ("patch", "field"),
    [
        ({"confidenceLow": 90}, "confidenceLow"),
        ({"confidenceLow": 70, "confidenceHigh": 70}, "confidenceLow"),
        ({"confidenceHigh": 101}, "confidenceHigh"),
        ({"confidenceLow": 0}, "confidenceLow"),
        ({"autoLockMinutes": 0}, "autoLockMinutes"),
        ({"autoLockMinutes": 1441}, "autoLockMinutes"),
        ({"badgeHours": 169}, "badgeHours"),
        ({"debriefQueueThreshold": 51}, "debriefQueueThreshold"),
        ({"debriefEarlyMin": 0}, "debriefEarlyMin"),
        ({"practiceName": "  "}, "practiceName"),
        ({"profileName": "x" * 121}, "profileName"),
        ({"locale": None}, "locale"),
    ],
)
async def test_invalid_settings_are_422_and_write_nothing(l2_world, app, patch, field):
    before = (sql("SELECT * FROM profile"), sql("SELECT * FROM settings"))
    async with api_client(app) as cl:
        res = await cl.patch("/api/settings", json={"debriefEarlyMin": 9, **patch})
    assert res.status_code == 422
    assert res.json()["error"] == {
        "code": "invalid_value", "message": res.json()["error"]["message"], "field": field,
    }  # fmt: skip
    assert (sql("SELECT * FROM profile"), sql("SELECT * FROM settings")) == before


async def test_a_locale_change_shows_in_auth_state_and_the_next_sentence(l2_world, app):
    w = l2_world
    doc = w.doc()
    async with api_client(app) as cl:
        before = (await cl.get(f"/api/documents/{doc}")).json()["suggestion"]["sentence"]
        await cl.patch("/api/settings", json={"locale": "fr"})
        state = (await cl.get("/api/auth/state")).json()
        after = (await cl.get(f"/api/documents/{doc}")).json()["suggestion"]["sentence"]
    assert state["locale"] == "fr" and before != after and after.startswith("Ce document")


# --- §15.2 system status ---


async def test_dev_status_reads_configuration_and_calls_no_model(l2_world, app, monkeypatch):
    def hermes_only(r: httpx.Request) -> httpx.Response:
        if r.url.host == "hermes":
            return httpx.Response(200, json={"version": "0.21.5"})
        return httpx.Response(500)

    seen = mock_http(monkeypatch, home, hermes_only)
    async with api_client(app) as cl:
        body = (await cl.get("/api/system/status")).json()
    assert body["env"] == "dev" and body["version"]
    assert body["mona"] == {"status": "online", "hermesVersion": "0.21.5"}
    assert body["llm"] == {
        "endpoint": "openrouter", "model": get_settings().mona_llm_model, "quantization": None,
        "contextPerSlot": None, "slots": None, "vramBytes": None,
    }  # fmt: skip
    assert body["database"] == "ok" and body["queues"]["llm"] == {"todo": 0, "doing": 0}
    assert 0 < body["disk"]["dataFreeBytes"] <= body["disk"]["dataTotalBytes"]
    assert body["privacy"] == {"cloudAi": True, "telegram": False}
    assert seen == ["http://hermes:8642/health"]


async def test_prod_status_probes_llama_swap_through_the_base_url(monkeypatch):
    prod = Settings(
        database_url=get_settings().database_url, mona_env="prod",
        mona_llm_base_url="http://llama-swap:8080/v1", mona_llm_model="qwen36",
    )  # fmt: skip
    monkeypatch.setattr(system, "get_settings", lambda: prod)

    def llama_swap(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "other"}, {"id": "qwen36"}]})
        if request.url.path == "/upstream/qwen36/props":
            return httpx.Response(200, json={
                "model_path": "/models/Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf", "total_slots": 2,
                "default_generation_settings": {"n_ctx": 65536},
            })  # fmt: skip
        return httpx.Response(404)

    seen = mock_http(monkeypatch, system, llama_swap)
    llm = await system.llm_status()
    assert llm == {
        "endpoint": "local", "model": "qwen36", "quantization": "Q4_K_XL",
        "context_per_slot": 65536, "slots": 2, "vram_bytes": None,
    }  # fmt: skip
    assert seen == [
        "http://llama-swap:8080/v1/models", "http://llama-swap:8080/upstream/qwen36/props",
    ]  # fmt: skip


async def test_a_failed_probe_gives_nulls(monkeypatch):
    prod = Settings(
        database_url=get_settings().database_url, mona_env="prod",
        mona_llm_base_url="http://llama-swap:8080/v1",
    )  # fmt: skip
    monkeypatch.setattr(system, "get_settings", lambda: prod)

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    mock_http(monkeypatch, system, down)
    llm = await system.llm_status()
    assert llm["endpoint"] == "local" and llm["model"] is None and llm["slots"] is None


def test_quantization_is_parsed_from_the_gguf_name():
    assert system.quantization("/m/Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf") == "Q4_K_XL"
    assert system.quantization("/m/model-IQ3_XXS.gguf") == "IQ3_XXS"
    assert system.quantization("/m/model.Q8_0.gguf") == "Q8_0"
    assert system.quantization("/m/model-bf16.gguf") == "BF16"
    assert system.quantization(None) is None


async def test_status_needs_a_session(l2_world, app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://t") as cl:
        res = await cl.get("/api/system/status")
    assert res.status_code == 401


__all__ = ["date"]

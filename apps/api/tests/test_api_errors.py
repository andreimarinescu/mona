"""C2 §1.2 one error envelope (§17 item 1) and the §2.7 exception list, exactly."""

import httpx
import psycopg
import pytest
from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import OperationalError

from mona.api import documents
from mona.app import create_app
from mona.settings import get_settings
from tests.api_client import api_client, new_session


class Info(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    message: str
    field: str | None = None
    details: dict | None = None


class Envelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    error: Info


@pytest.fixture
def app(l2_world):
    return create_app()


def sql(stmt: str, params: tuple = ()) -> list:
    with psycopg.connect(get_settings().libpq_url) as conn:
        cur = conn.execute(stmt, params)
        return cur.fetchall() if cur.description else []


def bare(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://t")


def check(res: httpx.Response, status: int, code: str) -> Envelope:
    assert res.status_code == status, res.text
    body = Envelope.model_validate(res.json())
    assert body.error.code == code
    return body


async def test_every_status_comes_in_the_envelope(l2_world, app, monkeypatch):
    w = l2_world
    doc = w.doc()
    ids = w.ids("entities")
    async with api_client(app) as cl, bare(app) as anon:
        v = check(await cl.get("/api/rules", params={"limit": 0}), 400, "invalid_request")
        assert v.error.field == "limit" and v.error.details["errors"][0]["field"] == "limit"
        bad_body = check(await cl.patch("/api/settings", json={"badgeHours": "x"}), 400,
                         "invalid_request")  # fmt: skip
        assert bad_body.error.field == "badgeHours"
        check(await anon.get("/api/rules"), 401, "unauthenticated")
        check(await anon.post("/api/auth/unlock", json={"password": "nope"}), 401,
              "invalid_password")  # fmt: skip
        check(await cl.post("/api/auth/heartbeat", headers={"x-csrf-token": "x"}), 403,
              "csrf_failed")  # fmt: skip
        check(await cl.delete(f"/api/entities/{ids['visitors']}"), 403, "not_allowed")
        check(await cl.get("/api/nowhere"), 404, "not_found")
        check(await cl.get("/api/documents/rul_" + "0" * 26), 404, "not_found")
        check(await cl.get(f"/api/documents/{doc}/thumbnail"), 404, "not_ready")
        check(await cl.post(f"/api/documents/{doc}/delete", json={"confirm": True,
              "fileName": "other.pdf"}), 422, "invalid_value")  # fmt: skip
        with monkeypatch.context() as m:
            read = documents.views.doc_row
            moved = {"current_path": "moved/other.pdf"}
            m.setattr(documents.views, "doc_row", lambda *a, **k: {**read(*a, **k), **moved})
            check(await cl.post(f"/api/documents/{doc}/delete", json={"confirm": True,
                  "fileName": "other.pdf"}), 409, "stale")  # fmt: skip
        check(await cl.delete(f"/api/entities/{ids['lmnp']}"), 409, "in_use")
        check(await cl.post("/api/auth/heartbeat", content=b"x" * (70 * 1024),
              headers={"content-type": "application/json"}), 413, "too_large")  # fmt: skip
        check(await cl.post("/api/auth/heartbeat", content=b"x=1",
              headers={"content-type": "text/plain"}), 415, "unsupported_media_type")  # fmt: skip
        broken = {"template": {"pathTemplate": "{oops", "fileTemplate": "{date}"}}
        check(await cl.patch("/api/categories/insurance", json=broken), 422, "invalid_template")
        check(await cl.patch(f"/api/rules/{w.rule_id('opco-cabinet')}", json={
            "action": {"entity": "nowhere"}}), 422, "invalid_rule")  # fmt: skip
        check(await cl.patch("/api/settings", json={"badgeHours": 0}), 422, "invalid_value")
        check(await cl.post(f"/api/documents/{doc}/confirm"), 422, "not_renderable")
        monkeypatch.setattr(documents, "_detail", _boom(RuntimeError("row text")))
        internal = check(await cl.get(f"/api/documents/{doc}"), 500, "internal")
        assert "row text" not in internal.error.message
        monkeypatch.setattr(documents, "_detail", _boom(OperationalError("x", {}, Exception())))
        check(await cl.get(f"/api/documents/{doc}"), 503, "unavailable")
    sql("UPDATE profile SET locked_at = now()")
    async with api_client(app) as cl:
        check(await cl.get("/api/rules"), 423, "locked")


def _boom(exc: Exception):
    def raise_it(*_a, **_k):
        raise exc

    return raise_it


async def test_too_many_attempts_is_429_with_retry_after(l2_world, app):
    async with bare(app) as anon:
        for _ in range(5):
            await anon.post("/api/auth/unlock", json={"password": "nope"})
        res = await anon.post("/api/auth/unlock", json={"password": "nope"})
    check(res, 429, "too_many_attempts")
    assert res.headers["retry-after"] == "60"


async def test_undo_errors_are_in_the_envelope(l2_world, app):
    w = l2_world
    doc = w.doc()
    entry = w.ctx.ops.delete(doc, actor="user", via="ui").entry_id
    async with api_client(app) as cl:
        await cl.post(f"/api/journal/{entry}/undo")
        check(await cl.post(f"/api/journal/{entry}/undo"), 409, "already_undone")


# --- §2.7: the exception list, exactly ---


async def test_lock_and_logout_skip_only_the_lock_check(l2_world, app):
    _, token = new_session()
    sql("UPDATE profile SET locked_at = now()")
    async with bare(app) as anon:
        for path in ("/api/auth/lock", "/api/auth/logout"):
            check(await anon.post(path), 401, "unauthenticated")
    async with api_client(app, token=token) as cl:
        for path in ("/api/auth/lock", "/api/auth/logout"):
            check(await cl.post(path, headers={"x-csrf-token": "wrong"}), 403, "csrf_failed")
    async with api_client(app, token=token) as cl:
        check(await cl.post("/api/auth/heartbeat"), 423, "locked")
        check(await cl.put("/api/auth/password", json={"currentPassword": "x",
              "newPassword": "long enough"}), 423, "locked")  # fmt: skip
        check(await cl.get("/api/settings"), 423, "locked")
        assert (await cl.post("/api/auth/lock")).status_code == 204


async def test_only_health_and_state_skip_the_session(l2_world, app):
    async with bare(app) as anon:
        assert (await anon.get("/api/health")).status_code == 200
        assert (await anon.get("/api/auth/state")).status_code == 200
        for method, path in (
            ("GET", "/api/shell"), ("POST", "/api/auth/heartbeat"),
            ("GET", "/api/auth/stateful"), ("POST", "/api/auth/state"),
        ):  # fmt: skip
            check(await anon.request(method, path), 401, "unauthenticated")


async def test_unlock_skips_session_lock_and_csrf_but_not_the_origin(l2_world, app):
    sql("UPDATE profile SET locked_at = now()")
    async with bare(app) as anon:
        ok = await anon.post("/api/auth/unlock", json={"password": "x"})
        check(await anon.post("/api/auth/unlock", json={"password": "x"},
              headers={"origin": "http://evil.example"}), 403, "csrf_failed")  # fmt: skip
    assert ok.status_code == 200

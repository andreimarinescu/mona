"""C2 §17 tests 2–4: unlock, sessions, the lock, CSRF and the service key."""

import asyncio
from datetime import timedelta

import httpx
import psycopg
import pytest

from mona import clock
from mona.api import auth
from mona.api.session import COOKIE, csrf_token, throttle
from mona.app import create_app
from mona.settings import get_settings
from tests.api_client import api_client, new_session, session_headers
from tests.conftest import SERVICE_KEY

PASSWORD = "x"
PROTECTED = "/api/conversations"


def sql(stmt: str, params: tuple = ()) -> list:
    with psycopg.connect(get_settings().libpq_url) as conn:
        cur = conn.execute(stmt, params)
        return cur.fetchall() if cur.description else []


@pytest.fixture
def l2_auth(clean):
    sql("DELETE FROM auth_sessions")
    sql("UPDATE profile SET locked_at = NULL, auto_lock_minutes = 15, locale = 'en'")
    throttle.reset()
    yield
    throttle.reset()


@pytest.fixture
def app():
    return create_app()


def client(app, base_url: str = "http://t", **kw) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url=base_url, **kw)


class Clock:
    def __init__(self, monkeypatch) -> None:
        self.at = clock.now()
        monkeypatch.setattr(clock, "now", lambda: self.at)

    def advance(self, **kw) -> None:
        self.at += timedelta(**kw)


async def test_no_cookie_is_401_and_the_envelope_names_the_code(l2_auth, app):
    async with client(app) as c:
        res = await c.get(PROTECTED)
    assert res.status_code == 401
    assert res.json() == {"error": {"code": "unauthenticated", "message": "No live session."}}


async def test_unlock_sets_a_strict_http_only_cookie_and_returns_the_csrf_token(l2_auth, app):
    async with client(app, base_url="http://localhost") as c:
        res = await c.post("/api/auth/unlock", json={"password": PASSWORD})
        assert res.status_code == 200
        cookie = res.headers["set-cookie"]
        assert "HttpOnly" in cookie and "SameSite=strict" in cookie and "Secure" in cookie
        token = res.cookies[COOKIE]
        assert len(token) == 43
        state = res.json()
        assert state["authenticated"] and not state["locked"]
        assert state["csrfToken"] == csrf_token(token)
        assert state["profileName"] and state["autoLockMinutes"] == 15
    async with client(app, cookies={COOKIE: token}) as c:
        assert (await c.get(PROTECTED)).status_code == 200
    [(stored,)] = sql("SELECT token_hash FROM auth_sessions")
    assert token not in stored and len(stored) == 64


async def test_cookie_is_not_secure_on_a_plain_http_host_or_an_untrusted_forwarded_proto(
    l2_auth, app
):
    async with client(app, base_url="http://mona.lan") as c:
        res = await c.post(
            "/api/auth/unlock", json={"password": PASSWORD}, headers={"x-forwarded-proto": "https"}
        )
    assert res.status_code == 200 and "Secure" not in res.headers["set-cookie"]


async def test_forwarded_https_from_the_trusted_proxy_makes_the_cookie_secure(l2_auth, monkeypatch):
    monkeypatch.setattr(get_settings(), "mona_trusted_proxy", "127.0.0.1")
    transport = httpx.ASGITransport(create_app(), client=("127.0.0.1", 5000))
    async with httpx.AsyncClient(transport=transport, base_url="http://mona.lan") as c:
        res = await c.post(
            "/api/auth/unlock", json={"password": PASSWORD}, headers={"x-forwarded-proto": "https"}
        )
    assert res.status_code == 200 and "Secure" in res.headers["set-cookie"]


async def test_wrong_password_is_401_without_a_cookie(l2_auth, app):
    async with client(app) as c:
        res = await c.post("/api/auth/unlock", json={"password": "nope"})
    assert res.status_code == 401 and res.json()["error"]["code"] == "invalid_password"
    assert "set-cookie" not in res.headers
    assert sql("SELECT count(*) FROM auth_sessions")[0][0] == 0


async def test_the_sixth_failure_in_the_window_is_429_with_retry_after(l2_auth, app, monkeypatch):
    clk = Clock(monkeypatch)
    async with client(app) as c:
        for _ in range(5):
            res = await c.post("/api/auth/unlock", json={"password": "nope"})
            assert res.status_code == 401
        res = await c.post("/api/auth/unlock", json={"password": PASSWORD})
        assert res.status_code == 429 and res.headers["retry-after"] == "60"
        assert res.json()["error"]["code"] == "too_many_attempts"
        clk.advance(seconds=61)
        assert (await c.post("/api/auth/unlock", json={"password": PASSWORD})).status_code == 200


async def test_a_success_resets_the_count(l2_auth, app):
    async with client(app) as c:
        for _ in range(4):
            await c.post("/api/auth/unlock", json={"password": "nope"})
        assert (await c.post("/api/auth/unlock", json={"password": PASSWORD})).status_code == 200
        for _ in range(4):
            res = await c.post("/api/auth/unlock", json={"password": "nope"})
            assert res.status_code == 401


async def test_a_burst_of_20_wrong_unlocks_verifies_at_most_5(l2_auth, app, monkeypatch):
    calls = 0
    real = auth.verify_password

    def counted(stored: str, password: str) -> bool:
        nonlocal calls
        calls += 1
        return real(stored, password)

    monkeypatch.setattr(auth, "verify_password", counted)
    async with client(app) as c:
        results = await asyncio.gather(
            *(c.post("/api/auth/unlock", json={"password": f"bad{i}"}) for i in range(20))
        )
    statuses = sorted(r.status_code for r in results)
    assert calls == 5
    assert statuses == [401] * 5 + [429] * 15


async def test_an_idle_session_is_locked_for_reads_and_writes(l2_auth, app, monkeypatch):
    clk = Clock(monkeypatch)
    _, token = new_session()
    async with api_client(app, token=token) as c:
        assert (await c.get(PROTECTED)).status_code == 200
        clk.advance(minutes=15)
        get = await c.get(PROTECTED)
        post = await c.post("/api/auth/heartbeat")
    assert get.status_code == 423 and get.json()["error"]["code"] == "locked"
    assert post.status_code == 423


async def test_polling_reads_never_keep_the_screen_unlocked(l2_auth, app, monkeypatch):
    clk = Clock(monkeypatch)
    _, token = new_session()
    async with api_client(app, token=token) as c:
        for _ in range(14):
            clk.advance(minutes=1)
            assert (await c.get(PROTECTED)).status_code == 200
        clk.advance(minutes=1)
        assert (await c.get(PROTECTED)).status_code == 423


async def test_a_heartbeat_keeps_the_session_unlocked(l2_auth, app, monkeypatch):
    clk = Clock(monkeypatch)
    _, token = new_session()
    async with api_client(app, token=token) as c:
        for _ in range(3):
            clk.advance(minutes=10)
            assert (await c.post("/api/auth/heartbeat")).status_code == 204
        clk.advance(minutes=10)
        assert (await c.get(PROTECTED)).status_code == 200


async def test_lock_locks_every_session_and_unlock_leaves_an_idle_one_locked(
    l2_auth, app, monkeypatch
):
    clk = Clock(monkeypatch)
    _, idle = new_session(last_active=clk.at - timedelta(minutes=20))
    _, other = new_session()
    _, mine = new_session()
    async with api_client(app, token=mine) as me, api_client(app, token=other) as them:
        assert (await them.get(PROTECTED)).status_code == 200
        assert (await me.post("/api/auth/lock")).status_code == 204
        assert (await them.get(PROTECTED)).status_code == 423
        assert (await me.get(PROTECTED)).status_code == 423
        res = await me.post("/api/auth/unlock", json={"password": PASSWORD})
        assert res.status_code == 200 and not res.json()["locked"]
        assert "set-cookie" not in res.headers
        assert (await me.get(PROTECTED)).status_code == 200
        assert (await them.get(PROTECTED)).status_code == 200
    async with api_client(app, token=idle) as stale:
        assert (await stale.get(PROTECTED)).status_code == 423


async def test_the_allowlist_answers_while_locked(l2_auth, app):
    _, token = new_session()
    sql("UPDATE profile SET locked_at = now()")
    async with api_client(app, token=token) as c:
        state = (await c.get("/api/auth/state")).json()
        assert state["authenticated"] and state["locked"] and state["profileName"] is None
        assert (await c.get("/api/health")).status_code == 200
        assert (await c.post("/api/auth/lock")).status_code == 204
        assert (await c.post("/api/auth/heartbeat")).status_code == 423
        assert (await c.post("/api/auth/logout")).status_code == 204
        assert (await c.get("/api/auth/state")).json()["authenticated"] is False


async def test_state_without_a_session_carries_only_the_locale(l2_auth, app):
    sql("UPDATE profile SET locale = 'fr'")
    async with client(app) as c:
        state = (await c.get("/api/auth/state")).json()
    assert state == {
        "authenticated": False, "locked": False, "locale": "fr", "csrfToken": None,
        "autoLockMinutes": None, "profileName": None,
    }  # fmt: skip


async def test_logout_revokes_this_session_and_clears_the_cookie(l2_auth, app):
    sid, token = new_session()
    async with api_client(app, token=token) as c:
        res = await c.post("/api/auth/logout")
        assert res.status_code == 204 and f'{COOKIE}=""' in res.headers["set-cookie"]
    async with api_client(app, token=token) as c:
        assert (await c.get(PROTECTED)).status_code == 401
    assert sql("SELECT revoked_at IS NOT NULL FROM auth_sessions WHERE id = %s", (sid,)) == [
        (True,)
    ]


async def test_expired_or_revoked_sessions_are_unauthenticated(l2_auth, app):
    _, expired = new_session(expires_in=timedelta(seconds=-1))
    rid, revoked = new_session()
    sql("UPDATE auth_sessions SET revoked_at = now() WHERE id = %s", (rid,))
    for token in (expired, revoked, "not-a-token"):
        async with api_client(app, token=token) as c:
            assert (await c.get(PROTECTED)).status_code == 401


@pytest.mark.parametrize(
    "foreign",
    ['prefs={"theme":"dark"}', "msg=hello world", "flag", "path=/a/b", 'x="', "=;;"],
)
async def test_a_malformed_foreign_cookie_does_not_hide_the_session(l2_auth, app, foreign):
    _, token = new_session()
    cookie = {"cookie": f"{foreign}; {COOKIE}={token}; after=1"}
    async with client(app, base_url="http://localhost", headers=cookie) as c:
        read = await c.get(PROTECTED)
        state = (await c.get("/api/auth/state")).json()
        unlocked = await c.post("/api/auth/unlock", json={"password": PASSWORD})
    assert read.status_code == 200
    assert state["authenticated"] and state["csrfToken"] == csrf_token(token)
    assert unlocked.status_code == 200 and "set-cookie" not in unlocked.headers
    assert sql("SELECT count(*) FROM auth_sessions") == [(1,)]


async def test_password_change_revokes_every_other_session(l2_auth, app):
    _, other = new_session()
    _, mine = new_session()
    async with api_client(app, token=mine) as c:
        wrong = await c.put(
            "/api/auth/password", json={"currentPassword": "nope", "newPassword": "long enough"}
        )
        short = await c.put(
            "/api/auth/password", json={"currentPassword": PASSWORD, "newPassword": "short"}
        )
        ok = await c.put(
            "/api/auth/password", json={"currentPassword": PASSWORD, "newPassword": "long enough"}
        )
        assert (await c.get(PROTECTED)).status_code == 200
    assert wrong.status_code == 401 and wrong.json()["error"]["code"] == "invalid_password"
    assert short.status_code == 422 and short.json()["error"]["field"] == "newPassword"
    assert ok.status_code == 204
    async with api_client(app, token=other) as c:
        assert (await c.get(PROTECTED)).status_code == 401
    async with client(app) as c:
        assert (await c.post("/api/auth/unlock", json={"password": "x"})).status_code == 401
        good = await c.post("/api/auth/unlock", json={"password": "long enough"})
        assert good.status_code == 200
    sql("UPDATE profile SET password_hash = %s", (auth.hasher.hash(PASSWORD),))


# --- CSRF (test 3) ---


@pytest.mark.parametrize("path", ["/api/auth/heartbeat", "/api/chat", "/api/intake"])
async def test_a_write_without_a_valid_csrf_token_is_403(l2_auth, app, path):
    _, token = new_session()
    _, other = new_session()
    async with client(app, cookies={COOKIE: token}) as c:
        missing = await c.post(path, json={})
        foreign = await c.post(path, json={}, headers=session_headers(other))
        bad_origin = await c.post(
            path, json={}, headers={**session_headers(token), "origin": "http://evil.example"}
        )
    for res in (missing, foreign, bad_origin):
        assert res.status_code == 403 and res.json()["error"]["code"] == "csrf_failed"


async def test_the_app_origin_and_the_configured_public_origin_pass(l2_auth, app, monkeypatch):
    _, token = new_session()
    async with api_client(app, token=token) as c:
        same = await c.post("/api/auth/heartbeat", headers={"origin": "http://t"})
        assert same.status_code == 204
        monkeypatch.setattr(get_settings(), "mona_public_origin", "https://mona.example")
        public = await c.post("/api/auth/heartbeat", headers={"origin": "https://mona.example"})
        host = await c.post("/api/auth/heartbeat", headers={"origin": "http://t"})
    assert public.status_code == 204 and host.status_code == 403


async def test_unlock_needs_no_token_but_checks_the_origin(l2_auth, app):
    async with client(app) as c:
        evil = await c.post(
            "/api/auth/unlock", json={"password": PASSWORD}, headers={"origin": "http://evil.x"}
        )
        fine = await c.post(
            "/api/auth/unlock", json={"password": PASSWORD}, headers={"origin": "http://t"}
        )
    assert evil.status_code == 403 and evil.json()["error"]["code"] == "csrf_failed"
    assert fine.status_code == 200


async def test_a_json_route_given_another_content_type_is_415(l2_auth, app):
    async with api_client(app) as c:
        res = await c.put(
            "/api/auth/password",
            content=b"currentPassword=x",
            headers={"content-type": "text/plain"},
        )
    assert res.status_code == 415 and res.json()["error"]["code"] == "unsupported_media_type"


# --- service key isolation (test 4) ---


async def test_the_service_key_is_no_session_on_api(l2_auth, app):
    _, token = new_session()
    bearer = {"authorization": f"Bearer {SERVICE_KEY}"}
    async with client(app) as c:
        alone = await c.get(PROTECTED, headers=bearer)
    async with client(app, cookies={COOKIE: token}) as c:
        assert (await c.get(PROTECTED)).status_code == 200
        with_cookie = await c.get(PROTECTED, headers=bearer)
    assert alone.status_code == 401 and with_cookie.status_code == 401


async def test_the_service_key_is_accepted_on_mcp(l2_auth, app):
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    headers = {
        "authorization": f"Bearer {SERVICE_KEY}",
        "accept": "application/json, text/event-stream",
    }
    async with app.router.lifespan_context(app), client(app) as c:
        res = await c.post("/mcp", json=body, headers=headers)
    assert res.status_code == 200


# --- `mona profile set-password` and housekeeping (§2.1, §2.2) ---


def test_set_password_is_prompted_and_ends_every_session(l2_auth):
    from typer.testing import CliRunner

    from mona.cli import app as cli

    _, token = new_session()
    runner = CliRunner()
    short = runner.invoke(cli, ["profile", "set-password"], input="short\nshort\n")
    res = runner.invoke(cli, ["profile", "set-password"], input="new secret\nnew secret\n")
    assert short.exit_code == 1 and res.exit_code == 0, res.output
    assert "new secret" not in res.output
    [(stored,)] = sql("SELECT password_hash FROM profile")
    assert auth.verify_password(stored, "new secret")
    assert sql("SELECT count(*) FROM auth_sessions WHERE revoked_at IS NULL") == [(0,)]
    sql("UPDATE profile SET password_hash = %s", (auth.hasher.hash(PASSWORD),))


async def test_housekeeping_deletes_sessions_dead_for_a_week(l2_auth):
    from mona.jobs import purge_auth_sessions

    old, _ = new_session(expires_in=timedelta(days=-8))
    revoked, _ = new_session()
    recent, _ = new_session(expires_in=timedelta(days=-1))
    live, _ = new_session()
    sql("UPDATE auth_sessions SET revoked_at = now() - interval '8 days' WHERE id = %s", (revoked,))
    assert await purge_auth_sessions.func(timestamp=0) == 2
    assert {r for (r,) in sql("SELECT id FROM auth_sessions")} == {recent, live}

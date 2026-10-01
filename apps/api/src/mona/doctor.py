"""`mona doctor`: one line per check, green, amber or red; any red fails the command."""

import os
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
import psycopg
import yaml

from mona import privacy
from mona.settings import Settings

GREEN, AMBER, RED = "green", "amber", "red"
ORDER = (
    "env", "settings", "postgres", "migrations", "queues", "workers", "hermes", "toolsets",
    "model", "gpu", "disk", "missing-files", "purge", "origin", "telegram", "exposure",
    "A1", "A2", "A3", "A4", "A5", "memory",
)  # fmt: skip
GIB = 1 << 30
DISK_AMBER, DISK_RED = 10 * GIB, 2 * GIB
QUEUE_AMBER = 50
HEARTBEAT_S = 60
PURGE_GRACE_H = 1
SLOT_CONTEXT = 65536
PROBE_S = 3.0
OPENROUTER_KEY_URL = "https://openrouter.ai/api/v1/key"
MONEY = re.compile(r"\d[\d ., ]*\s?(?:€|EUR|RON|lei)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Check:
    name: str
    level: str
    detail: str


def parse_host_lines(text: str) -> list[Check]:
    """`level<TAB>name<TAB>detail`, as printed by deploy/bin/doctor-host."""
    out = []
    for raw in text.splitlines():
        parts = raw.rstrip("\n").split("\t")
        if len(parts) < 3 or parts[0] not in (GREEN, AMBER, RED):
            continue
        out.append(Check(parts[1], parts[0], parts[2]))
    return out


def ordered(checks: Iterable[Check]) -> list[Check]:
    return sorted(checks, key=lambda c: ORDER.index(c.name) if c.name in ORDER else len(ORDER))


def worst(checks: Iterable[Check]) -> str:
    levels = {c.level for c in checks}
    return RED if RED in levels else AMBER if AMBER in levels else GREEN


def render(checks: Iterable[Check], color: bool = False) -> list[str]:
    paint = {GREEN: "\033[32m", AMBER: "\033[33m", RED: "\033[31m"}
    lines = []
    for c in checks:
        tag = c.level.upper().ljust(5)
        tag = f"{paint[c.level]}{tag}\033[0m" if color else tag
        lines.append(f"{tag} {c.name:<13} {c.detail}")
    return lines


def _ok(name: str, detail: str) -> Check:
    return Check(name, GREEN, detail)


def _bad(name: str, detail: str, level: str = RED) -> Check:
    return Check(name, level, detail)


def check_postgres(conninfo: str) -> tuple[Check, psycopg.Connection | None]:
    try:
        conn = psycopg.connect(conninfo, connect_timeout=int(PROBE_S), autocommit=True)
        conn.execute("SELECT 1")
    except psycopg.Error as e:
        return _bad("postgres", f"unreachable ({type(e).__name__})"), None
    return _ok("postgres", "accepting connections"), conn


def check_migrations(conn: psycopg.Connection, head: str) -> Check:
    try:
        row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        jobs = conn.execute("SELECT to_regclass('procrastinate_jobs')").fetchone()
    except psycopg.Error:
        return _bad("migrations", "alembic_version is missing: run `mona migrate`")
    current = row[0] if row else None
    if current != head:
        return _bad("migrations", f"at {current or 'none'}, head is {head}: run `mona migrate`")
    if not jobs or jobs[0] is None:
        return _bad("migrations", "the job queue schema is missing: run `mona migrate`")
    return _ok("migrations", f"at head {head}")


def check_queues(conn: psycopg.Connection) -> list[Check]:
    depth = {
        (q, s): n
        for q, s, n in conn.execute(
            "SELECT queue_name, status::text, count(*) FROM procrastinate_jobs"
            " WHERE status IN ('todo', 'doing') GROUP BY 1, 2"
        )
    }
    stalled = conn.execute(
        "SELECT count(*) FROM procrastinate_jobs j"
        " LEFT JOIN procrastinate_workers w ON w.id = j.worker_id"
        " WHERE j.status = 'doing'"
        " AND (w.id IS NULL OR w.last_heartbeat < now() - make_interval(secs => %s))",
        (HEARTBEAT_S,),
    ).fetchone()[0]
    alive = conn.execute(
        "SELECT count(*) FROM procrastinate_workers"
        " WHERE last_heartbeat >= now() - make_interval(secs => %s)",
        (HEARTBEAT_S,),
    ).fetchone()[0]
    parts = [
        f"{q} {depth.get((q, 'todo'), 0)} waiting, {depth.get((q, 'doing'), 0)} running"
        for q in ("llm", "cpu")
    ]
    waiting = max(depth.get((q, "todo"), 0) for q in ("llm", "cpu"))
    if stalled:
        queues = _bad("queues", f"{stalled} stalled jobs; " + "; ".join(parts))
    elif waiting > QUEUE_AMBER:
        queues = _bad("queues", "; ".join(parts), AMBER)
    else:
        queues = _ok("queues", "; ".join(parts))
    if alive == 0:
        workers = _bad("workers", "no worker is running: queued jobs will not move")
    elif alive < 2:
        workers = _bad("workers", "1 worker is running, expected 2 (llm, cpu)", AMBER)
    else:
        workers = _ok("workers", f"{alive} running")
    return [queues, workers]


def check_missing_files(conn: psycopg.Connection) -> Check:
    n = conn.execute(
        "SELECT count(*) FROM documents"
        " WHERE pipeline_error = 'missing_file' AND deleted_at IS NULL"
    ).fetchone()[0]
    if n:
        return _bad("missing-files", f"{n} documents whose file is gone (C7 invariant 1)")
    return _ok("missing-files", "none")


def check_purge(conn: psycopg.Connection) -> Check:
    hours = conn.execute(
        "SELECT purge_after_hours FROM entities WHERE purge_after_hours IS NOT NULL"
    ).fetchone()
    if hours is None:
        return _ok("purge", "no Visitors entity yet")
    overdue = conn.execute(
        "SELECT count(*) FROM documents d JOIN batches b ON b.id = d.batch_id"
        " WHERE b.visitor AND d.arrived_at + make_interval(hours => %s) <= now()",
        (hours[0] + PURGE_GRACE_H,),
    ).fetchone()[0]
    if overdue:
        return _bad(
            "purge", f"{overdue} visitor documents are past their purge time by over an hour"
        )
    return _ok("purge", f"no visitor document overdue (purge after {hours[0]} h)")


def check_disk(path: Path) -> Check:
    try:
        st = os.statvfs(path)
    except OSError:
        return _bad("disk", f"{path} is not readable")
    free = st.f_bavail * st.f_frsize
    detail = f"{free / GIB:.1f} GiB free on {path}"
    if free < DISK_RED:
        return _bad("disk", detail)
    if free < DISK_AMBER:
        return _bad("disk", detail, AMBER)
    return _ok("disk", detail)


def check_origin(origin: str | None) -> Check:
    if not origin:
        return _bad("origin", "MONA_PUBLIC_ORIGIN is not set: every browser write would be refused")
    try:
        parts = urlsplit(origin)
        port = parts.port
    except ValueError:
        return _bad("origin", "MONA_PUBLIC_ORIGIN is not a valid URL")
    problems = []
    if parts.scheme not in ("http", "https") or not parts.hostname:
        problems.append("it must be http(s)://host[:port]")
    if parts.path not in ("", "/") or parts.query or parts.fragment or parts.username:
        problems.append("it must have no path, query or credentials")
    if origin.endswith("/"):
        problems.append("it must not end with a slash")
    if problems:
        return _bad("origin", "MONA_PUBLIC_ORIGIN is malformed: " + "; ".join(problems))
    return _ok("origin", f"open exactly {origin}" + ("" if port else " (default port)"))


def check_telegram(s: Settings) -> Check:
    if s.telegram_bot_token and s.telegram_bot_token.get_secret_value().strip():
        return _ok("telegram", "token set (not probed)")
    return _ok("telegram", "not configured (deferred)")


def hermes_checks(s: Settings, client: httpx.Client) -> list[Check]:
    try:
        res = client.get(f"{s.hermes_url}/health")
        body = res.json() if res.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        body = None
    if body is None:
        health = _bad("hermes", "does not answer /health")
    else:
        version = body.get("version") if isinstance(body, dict) else None
        health = _ok("hermes", f"healthy, version {version or 'unknown'}")
    return [health, check_toolsets(s.mona_hermes_home)]


def check_toolsets(home: Path | None) -> Check:
    if home is None:
        return _bad("toolsets", "MONA_HERMES_HOME is not set: profile not inspected", AMBER)
    try:
        cfg = yaml.safe_load((home / "config.yaml").read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return _bad("toolsets", "config.yaml is missing or unreadable in the Hermes profile")
    if cfg.get("platform_toolsets") != privacy.PLATFORM_TOOLSETS:
        return _bad("toolsets", "platform_toolsets differs from C4 §1.3")
    return _ok("toolsets", "api_server [memory, mona], telegram [memory, mona_tg], cron [mona_tg]")


def _json(client: httpx.Client, url: str) -> Any:
    try:
        res = client.get(url)
        return res.json() if res.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        return None


def _running(body: Any) -> list[dict[str, Any]]:
    items = body.get("running") if isinstance(body, dict) else body
    return [m for m in items or [] if isinstance(m, dict)]


def local_model_check(s: Settings, base: str, client: httpx.Client) -> Check:
    base = base.rstrip("/")
    root = base.removesuffix("/v1")
    models = _json(client, f"{base}/models")
    if models is None:
        return _bad("model", f"no answer from {urlsplit(base).netloc}")
    ids = [m.get("id") for m in models.get("data", []) if isinstance(m, dict)]
    if s.mona_llm_model not in ids:
        return _bad(
            "model", f"{s.mona_llm_model} is not served (serves {', '.join(ids) or 'none'})"
        )
    running = {m.get("model"): m.get("state") for m in _running(_json(client, f"{root}/running"))}
    if s.mona_llm_model not in running:
        return _bad("model", f"{s.mona_llm_model} served, not loaded yet", AMBER)
    state = running[s.mona_llm_model]
    if state and state != "ready":
        return _bad("model", f"{s.mona_llm_model} is {state}", AMBER)
    props = _json(client, f"{root}/upstream/{s.mona_llm_model}/props") or {}
    gen = props.get("default_generation_settings") or {}
    slots, context = props.get("total_slots"), gen.get("n_ctx") or props.get("n_ctx")
    detail = f"{s.mona_llm_model} loaded, {slots or '?'} slots x {context or '?'} context"
    if not slots or not context:
        return _bad("model", f"{detail} (props unreadable)", AMBER)
    if slots < 2 or context < SLOT_CONTEXT:
        return _bad("model", f"{detail}; wanted 2 x {SLOT_CONTEXT}", AMBER)
    return _ok("model", detail)


def openrouter_check(s: Settings, client: httpx.Client) -> Check:
    key = s.openrouter_api_key.get_secret_value() if s.openrouter_api_key else ""
    if not key:
        return _bad("model", "dev: OPENROUTER_API_KEY is not set", AMBER)
    try:
        res = client.get(OPENROUTER_KEY_URL, headers={"Authorization": f"Bearer {key}"})
    except httpx.HTTPError:
        return _bad("model", "dev: OpenRouter is unreachable")
    if res.status_code == 200:
        return _ok("model", f"dev: OpenRouter reachable, serving {s.mona_llm_model}")
    if res.status_code in (401, 403):
        return _bad("model", "dev: OpenRouter rejected the key")
    return _bad("model", f"dev: OpenRouter answered {res.status_code}")


def model_check(s: Settings, make_client: Callable[[], httpx.Client]) -> Check:
    """Prod only ever talks to the checked local endpoint; dev reaches OpenRouter when unset."""
    try:
        endpoint = privacy.model_endpoint(s)
    except privacy.ProdCheckFailed:
        return _bad("model", "MONA_LLM_BASE_URL fails the prod assertion (A2)")
    with make_client() as client:
        if endpoint.local:
            return local_model_check(s, endpoint.base_url, client)
        if s.mona_env == "prod":
            return _bad("model", "no local endpoint in prod")
        return openrouter_check(s, client)


def privacy_checks(
    s: Settings,
    env: Mapping[str, str],
    *,
    memory: bool = False,
    resolve: privacy.Resolver = privacy._resolve,
) -> list[Check]:
    out = []

    def run(name: str, ok: str, fn: Callable[[], None]) -> None:
        try:
            fn()
        except privacy.ProdCheckFailed as e:
            out.append(_bad(name, str(e).split(": ", 1)[-1]))
        else:
            out.append(_ok(name, ok))

    run("A1", "no cloud key in this environment", lambda: privacy.check_env(env, "A1"))
    run(
        "A2", "model endpoint is local",
        lambda: privacy.require_local_llm(s.mona_llm_base_url, resolve),
    )  # fmt: skip
    if s.mona_hermes_home is not None:
        home = s.mona_hermes_home
        run(
            "A4",
            "no cloud key in the profile .env",
            lambda: privacy.check_hermes_env_file(home / ".env"),
        )
        run(
            "A5", "Hermes config is the prod lockdown",
            lambda: privacy.check_hermes_config(home / "config.yaml", env, resolve),
        )  # fmt: skip
        if memory:
            out.append(memory_scan(home / "memories"))
    return out


def memory_scan(folder: Path) -> Check:
    """C9 §3.4: Hermes memory holds no IBAN or amount."""
    from mona.iban import iban_candidates

    hits = []
    for path in sorted(folder.glob("*")) if folder.is_dir() else []:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if iban_candidates(text):
            hits.append(f"{path.name}: IBAN")
        if MONEY.search(text):
            hits.append(f"{path.name}: amount")
    if hits:
        return _bad("memory", "; ".join(hits))
    return _ok("memory", "no IBAN or amount in the Hermes memory files")


def run_checks(
    s: Settings,
    env: Mapping[str, str],
    *,
    head: str,
    client: Callable[[], httpx.Client] | None = None,
    host: Iterable[Check] = (),
    privacy_asked: bool = False,
    resolve: privacy.Resolver = privacy._resolve,
) -> list[Check]:
    """Every in-container check; `host` are the lines the host wrapper collected."""
    make = client or (lambda: httpx.Client(timeout=PROBE_S))
    guarded = s.mona_env == "prod"

    def probe_client() -> httpx.Client:
        c = make()
        if guarded:
            c.event_hooks["request"] = [lambda r: privacy.guard_model_url(str(r.url), s)]
        return c

    checks = [_ok("env", s.mona_env)]
    pg, conn = check_postgres(s.libpq_url)
    checks.append(pg)
    if conn is None:
        for name in ("migrations", "queues", "workers", "missing-files", "purge"):
            checks.append(_bad(name, "skipped: no database", AMBER))
    else:
        with conn:
            checks.append(check_migrations(conn, head))
            checks += check_queues(conn)
            checks.append(check_missing_files(conn))
            checks.append(check_purge(conn))
    with make() as hermes_client:
        checks += hermes_checks(s, hermes_client)
    checks.append(model_check(s, probe_client))
    checks.append(check_disk(s.mona_data_dir))
    checks.append(check_origin(s.mona_public_origin))
    checks.append(check_telegram(s))
    if s.mona_env == "prod" or privacy_asked:
        checks += privacy_checks(s, env, memory=privacy_asked, resolve=resolve)
    host = list(host)
    if not any(c.name == "gpu" for c in host):
        host.append(_bad("gpu", "not checked: run through deploy/bin/mona doctor", AMBER))
    return ordered([*checks, *host])

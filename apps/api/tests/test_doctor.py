"""`mona doctor` (L6): each check green, amber and red, the exit code, and the host lines."""

import json
import os
import shutil
import stat
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
import yaml
from typer.testing import CliRunner

from mona import doctor as d
from mona.cli import app
from mona.migrate import head_revision
from mona.settings import Settings, get_settings
from tests import rows

ROOT = Path(__file__).resolve().parents[3]
DEV_PROFILE = ROOT / "deploy" / "hermes" / "config.yaml"
PROD_PROFILE = ROOT / "deploy" / "hermes" / "config.prod.yaml"
HOST = ROOT / "deploy" / "bin" / "doctor-host"
MODEL = "qwen-test"
FIXTURE_KEY = "sk-or-v1-fixture-value-never-printed"
LOCAL = "http://llama-swap:8080/v1"
PROD_ENV = {"MONA_LLM_BASE_URL": LOCAL, "MONA_LLM_MODEL": MODEL}


def by_name(checks: list[d.Check]) -> dict[str, d.Check]:
    return {c.name: c for c in checks}


def settings(tmp_path: Path, **kw) -> Settings:
    home = tmp_path / "hermes"
    home.mkdir(exist_ok=True)
    shutil.copy(kw.pop("profile", DEV_PROFILE), home / "config.yaml")
    base = {
        "database_url": get_settings().database_url,
        "mona_env": "dev",
        "mona_data_dir": tmp_path,
        "mona_hermes_home": home,
        "mona_public_origin": "http://localhost:5173",
        "mona_llm_model": MODEL,
        "openrouter_api_key": "fixture",
    }
    return Settings(**{**base, **kw})


def stack(
    *, hermes: bool = True, openrouter: int = 200, slots: int = 2, ctx: int = 65536,
    state: str = "ready", served: tuple[str, ...] = (MODEL,),
) -> Callable[[], httpx.Client]:  # fmt: skip
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/health":
            return (
                httpx.Response(200, json={"status": "ok", "version": "0.21.5"})
                if hermes
                else (httpx.Response(503))
            )
        if request.url.host == "openrouter.ai":
            return httpx.Response(openrouter, json={})
        if path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": m} for m in served]})
        if path == "/running":
            return httpx.Response(200, json={"running": [{"model": MODEL, "state": state}]})
        if path == f"/upstream/{MODEL}/props":
            return httpx.Response(
                200, json={"total_slots": slots, "default_generation_settings": {"n_ctx": ctx}}
            )
        return httpx.Response(404)

    return lambda: httpx.Client(transport=httpx.MockTransport(handler))


def run(s: Settings, *, client=None, host: str = "green\tgpu\tfixture GPU", **kw) -> dict:
    make = client if client is not None else stack()
    checks = d.run_checks(
        s, PROD_ENV, head=head_revision(), client=make, host=d.parse_host_lines(host), **kw
    )
    return by_name(checks)


@pytest.fixture
def db(clean):
    return clean


def test_everything_green_on_a_healthy_dev_stack(db, tmp_path, monkeypatch):
    s = settings(tmp_path)
    monkeypatch.setattr(d, "check_disk", lambda p: d.Check("disk", d.GREEN, "fixture"))
    with psycopg_workers(2):
        checks = run(s, client=stack())
    assert {n: c.level for n, c in checks.items()} == {n: d.GREEN for n in checks}, checks
    assert d.worst(checks.values()) == d.GREEN
    assert list(checks) == [n for n in d.ORDER if n in checks]
    assert checks["origin"].detail == "open exactly http://localhost:5173"


class psycopg_workers:
    """Two live Procrastinate workers' heartbeats, removed on exit."""

    def __init__(self, n: int):
        self.n = n

    def __enter__(self):
        with rows.connect() as conn:
            conn.execute("DELETE FROM procrastinate_workers")
            for _ in range(self.n):
                conn.execute("INSERT INTO procrastinate_workers DEFAULT VALUES")

    def __exit__(self, *exc):
        with rows.connect() as conn:
            conn.execute("UPDATE procrastinate_jobs SET worker_id = NULL")
            conn.execute("DELETE FROM procrastinate_workers")


def test_postgres_down_is_red_and_the_rest_of_the_database_checks_are_skipped(tmp_path):
    dead = "postgresql+psycopg://x:y@127.0.0.1:1/z"
    checks = run(settings(tmp_path, database_url=dead))
    assert checks["postgres"].level == d.RED
    for name in ("migrations", "queues", "workers", "missing-files", "purge"):
        assert checks[name].level == d.AMBER and "no database" in checks[name].detail
    assert d.worst(checks.values()) == d.RED


def test_a_database_behind_head_is_red(db, tmp_path):
    with rows.connect() as conn:
        conn.execute("UPDATE alembic_version SET version_num = 'old'")
    try:
        c = run(settings(tmp_path))["migrations"]
    finally:
        with rows.connect() as conn:
            conn.execute("UPDATE alembic_version SET version_num = %s", (head_revision(),))
    assert c.level == d.RED and "mona migrate" in c.detail


def test_a_stalled_job_is_red_and_a_missing_worker_is_flagged(db, tmp_path):
    with rows.connect() as conn:
        conn.execute(
            "INSERT INTO procrastinate_jobs (queue_name, task_name, status)"
            " VALUES ('llm', 'classify_document', 'doing')"
        )
    try:
        checks = run(settings(tmp_path))
    finally:
        with rows.connect() as conn:
            conn.execute("DELETE FROM procrastinate_jobs")
    assert checks["queues"].level == d.RED and "1 stalled" in checks["queues"].detail
    assert checks["workers"].level == d.RED


def test_one_worker_is_amber_and_a_deep_queue_is_amber(db, tmp_path):
    with rows.connect() as conn:
        for _ in range(d.QUEUE_AMBER + 1):
            conn.execute(
                "INSERT INTO procrastinate_jobs (queue_name, task_name) VALUES ('cpu', 'x')"
            )
    try:
        with psycopg_workers(1):
            checks = run(settings(tmp_path))
    finally:
        with rows.connect() as conn:
            conn.execute("DELETE FROM procrastinate_jobs")
    assert checks["queues"].level == d.AMBER and checks["workers"].level == d.AMBER


def test_a_document_without_its_file_is_red(db, tmp_path):
    doc = rows.document("Synthetic notice", entity="cabinet", status="filed")
    with rows.connect() as conn:
        conn.execute("UPDATE documents SET pipeline_error = 'missing_file' WHERE id = %s", (doc,))
    c = run(settings(tmp_path))["missing-files"]
    assert c.level == d.RED and c.detail.startswith("1 documents")


def test_a_visitor_document_past_its_purge_time_is_red_but_not_when_only_just_due(db, tmp_path):
    batch = rows.batch()
    with rows.connect() as conn:
        conn.execute("UPDATE batches SET visitor = true WHERE id = %s", (batch,))
    doc = rows.document("Synthetic visitor letter", entity="visiteurs", batch_id=batch)
    set_age = "UPDATE documents SET arrived_at = now() - make_interval(hours => %s) WHERE id = %s"
    with rows.connect() as conn:
        conn.execute(set_age, (24, doc))
    assert run(settings(tmp_path))["purge"].level == d.GREEN
    with rows.connect() as conn:
        conn.execute(set_age, (26, doc))
    c = run(settings(tmp_path))["purge"]
    assert c.level == d.RED and "1 visitor documents" in c.detail


@pytest.mark.parametrize(
    ("origin", "level"),
    [
        ("http://localhost:5173", d.GREEN),
        ("https://mona.example.org", d.GREEN),
        (None, d.RED),
        ("localhost:5173", d.RED),
        ("http://localhost:5173/", d.RED),
        ("http://localhost:5173/app", d.RED),
        ("ftp://localhost", d.RED),
        ("http://localhost:99999", d.RED),
        ("http://user@localhost", d.RED),
    ],
)
def test_the_public_origin_must_be_set_and_well_formed(origin, level):
    assert d.check_origin(origin).level == level


def test_hermes_down_is_red(db, tmp_path):
    assert run(settings(tmp_path), client=stack(hermes=False))["hermes"].level == d.RED


def test_the_toolsets_come_from_the_installed_profile(db, tmp_path):
    s = settings(tmp_path)
    assert run(s)["toolsets"].level == d.GREEN
    cfg = yaml.safe_load(DEV_PROFILE.read_text())
    cfg["platform_toolsets"]["api_server"] = ["memory", "mona", "terminal"]
    (s.mona_hermes_home / "config.yaml").write_text(yaml.safe_dump(cfg))
    assert run(s)["toolsets"].level == d.RED
    assert d.check_toolsets(None).level == d.AMBER


@pytest.mark.parametrize(
    ("kw", "level", "says"),
    [
        ({}, d.GREEN, "2 slots x 65536"),
        ({"slots": 1}, d.AMBER, "wanted 2 x 65536"),
        ({"ctx": 32768}, d.AMBER, "wanted 2 x 65536"),
        ({"state": "starting"}, d.AMBER, "starting"),
        ({"served": ("other",)}, d.RED, "is not served"),
    ],
)
def test_the_local_model_check(db, tmp_path, kw, level, says):
    s = settings(tmp_path, mona_llm_base_url=LOCAL)
    c = run(s, client=stack(**kw))["model"]
    assert c.level == level and says in c.detail


def test_a_local_model_that_does_not_answer_is_red(db, tmp_path):

    def down() -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(502)))

    assert run(settings(tmp_path, mona_llm_base_url=LOCAL), client=down)["model"].level == d.RED


@pytest.mark.parametrize(("status", "level"), [(200, d.GREEN), (401, d.RED), (500, d.RED)])
def test_dev_probes_openrouter_with_its_key(db, tmp_path, status, level):
    assert run(settings(tmp_path), client=stack(openrouter=status))["model"].level == level


def test_prod_never_probes_the_cloud(db, tmp_path):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.host)
        return httpx.Response(200, json={})

    s = settings(tmp_path, mona_env="prod", profile=PROD_PROFILE, mona_llm_base_url=None)
    c = run(s, client=lambda: httpx.Client(transport=httpx.MockTransport(handler)))["model"]
    assert c.level == d.RED and "openrouter.ai" not in seen


def test_the_prod_probes_are_confined_to_the_endpoint_host(db, tmp_path):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.host)
        return httpx.Response(404)

    s = settings(tmp_path, mona_env="prod", profile=PROD_PROFILE, mona_llm_base_url=LOCAL)
    run(s, client=lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    assert set(seen) <= {"llama-swap", "hermes"}


def test_disk_thresholds(tmp_path, monkeypatch):
    gib = 1 << 30

    def fake(free: int):
        return lambda p: os.statvfs_result(
            (4096, 4096, 100 * gib, free // 4096, free // 4096, 0, 0, 0, 0, 255)
        )

    for free, level in ((50 * gib, d.GREEN), (5 * gib, d.AMBER), (gib, d.RED)):
        monkeypatch.setattr(os, "statvfs", fake(free))
        assert d.check_disk(tmp_path).level == level
    monkeypatch.undo()
    assert d.check_disk(tmp_path / "missing").level == d.RED


def test_telegram_is_not_configured_by_default(tmp_path):
    c = d.check_telegram(settings(tmp_path))
    assert c.level == d.GREEN and "not configured" in c.detail


def test_prod_runs_the_privacy_assertions_and_names_keys_without_values(db, tmp_path):
    s = settings(tmp_path, mona_env="prod", profile=PROD_PROFILE, mona_llm_base_url=LOCAL)
    ok = run(s, host="green\tgpu\tx\ngreen\tA3\tx")
    assert [ok[n].level for n in ("A1", "A2", "A3", "A4", "A5")] == [d.GREEN] * 5
    checks = d.run_checks(
        s, {**PROD_ENV, "OPENROUTER_API_KEY": FIXTURE_KEY}, head=head_revision(), client=stack()
    )
    a1 = by_name(checks)["A1"]
    assert a1.level == d.RED and "OPENROUTER_API_KEY" in a1.detail
    assert FIXTURE_KEY not in a1.detail


def test_a_bad_profile_fails_a5_and_the_memory_scan_finds_an_iban(db, tmp_path):
    s = settings(tmp_path, mona_env="prod", profile=PROD_PROFILE, mona_llm_base_url=LOCAL)
    cfg = yaml.safe_load(PROD_PROFILE.read_text())
    cfg["agent"]["disabled_toolsets"].remove("terminal")
    (s.mona_hermes_home / "config.yaml").write_text(yaml.safe_dump(cfg))
    memories = s.mona_hermes_home / "memories"
    memories.mkdir()
    (memories / "MEMORY.md").write_text(
        "Pays to FR14 2004 1010 0505 0001 3M02 606 and 1 284,60 EUR"
    )
    checks = by_name(
        d.run_checks(s, PROD_ENV, head=head_revision(), client=stack(), privacy_asked=True)
    )
    assert checks["A5"].level == d.RED and "terminal" in checks["A5"].detail
    assert checks["memory"].level == d.RED
    assert "IBAN" in checks["memory"].detail and "amount" in checks["memory"].detail
    assert "FR14" not in checks["memory"].detail


def test_dev_hides_the_privacy_section_unless_asked(db, tmp_path):
    assert "A1" not in run(settings(tmp_path))
    assert run(settings(tmp_path), privacy_asked=True)["A1"].level == d.GREEN


def test_a_missing_gpu_line_is_amber_and_host_lines_are_parsed():
    lines = "red\texposure\tpublished: api:8765\nnoise\ngreen\tgpu\tRTX\n"
    assert [(c.name, c.level) for c in d.parse_host_lines(lines)] == [
        ("exposure", d.RED), ("gpu", d.GREEN),
    ]  # fmt: skip


def test_render_is_one_line_per_check_with_the_level_word():
    lines = d.render([d.Check("postgres", d.GREEN, "ok"), d.Check("hermes", d.RED, "down")])
    assert lines == ["GREEN postgres      ok", "RED   hermes        down"]


# --- the CLI: exit codes ---


def cli_env(tmp_path: Path, monkeypatch, **kw) -> None:
    s = settings(tmp_path, **kw)
    monkeypatch.setenv("MONA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MONA_HERMES_HOME", str(s.mona_hermes_home))
    monkeypatch.setenv("MONA_PUBLIC_ORIGIN", "http://localhost:5173")
    monkeypatch.setenv("HERMES_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("MONA_LLM_BASE_URL", "http://127.0.0.1:1/v1")
    monkeypatch.delenv("MONA_ENV", raising=False)
    monkeypatch.setenv("MONA_ENV", "dev")


def test_the_cli_exits_one_when_a_check_is_red(db, tmp_path, monkeypatch):
    cli_env(tmp_path, monkeypatch)
    res = CliRunner().invoke(app, ["doctor", "--host-lines", "-"], input="green\tgpu\tfixture\n")
    assert res.exit_code == 1, res.output
    assert "RED   hermes" in res.output and "GREEN postgres" in res.output
    assert "GREEN gpu" in res.output


def test_the_cli_json_mode(db, tmp_path, monkeypatch):
    cli_env(tmp_path, monkeypatch)
    res = CliRunner().invoke(app, ["doctor", "--json"])
    parsed = [json.loads(line) for line in res.output.splitlines()]
    assert parsed[0] == {"name": "env", "level": "green", "detail": "dev"}


def test_the_cli_reports_a_broken_configuration_instead_of_crashing(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL")
    res = CliRunner().invoke(app, ["doctor"])
    assert res.exit_code == 1 and res.output.startswith("RED   settings")


# --- deploy/bin/doctor-host, with fake nvidia-smi and docker ---


def fake_bin(tmp_path: Path, scripts: dict[str, str]) -> dict[str, str]:
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    for name, body in scripts.items():
        path = bindir / name
        path.write_text("#!/bin/sh\n" + body)
        path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return {"PATH": str(bindir), "MONA_ROOT": str(tmp_path)}


def host(tmp_path: Path, scripts: dict[str, str], *args: str) -> dict[str, tuple[str, str]]:
    env = fake_bin(tmp_path, scripts)
    out = subprocess.run(
        [sys.executable, str(HOST), *args], env={**env, "HOME": str(tmp_path)},
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    parsed = [line.split("\t") for line in out.stdout.splitlines()]
    return {name: (level, detail) for level, name, detail in parsed}


def compose_stub(env: str, publishers: str, container_env: str) -> dict[str, str]:
    rendered = json.dumps({"services": {"api": {"environment": {"MONA_ENV": env}}}})
    ps = json.dumps([{"Service": "caddy", "Publishers": json.loads(publishers)}])
    return {
        "docker": f"""
case "$*" in
  *"config"*) echo '{rendered}' ;;
  *" ps -q"*) echo c1 ;;
  *"ps"*) echo '{ps}' ;;
  *inspect*) printf '/mona-api-1\\t%s\\n' '{container_env}' ;;
esac
""",
    }


NVIDIA_OK = "echo 'NVIDIA GeForce RTX 5060 Ti, 9000, 16311'"


def test_host_gpu_line(tmp_path):
    scripts = {"nvidia-smi": NVIDIA_OK, **compose_stub("dev", "[]", "[]")}
    level, detail = host(tmp_path, scripts)["gpu"]
    assert level == "green" and "RTX 5060 Ti" in detail and "8.8 of 15.9 GiB" in detail
    tight = {**scripts, "nvidia-smi": "echo 'GPU, 15800, 16311'"}
    assert host(tmp_path, tight)["gpu"][0] == "amber"


@pytest.mark.parametrize(("env", "level"), [("dev", "amber"), ("prod", "red")])
def test_host_without_a_gpu(tmp_path, env, level):
    assert host(tmp_path, compose_stub(env, "[]", "[]"))["gpu"][0] == level


def test_host_exposure(tmp_path):
    loopback = '[{"URL": "127.0.0.1", "PublishedPort": 8080}]'
    wide = '[{"URL": "0.0.0.0", "PublishedPort": 8080}]'
    assert host(tmp_path, compose_stub("dev", loopback, "[]"))["exposure"][0] == "green"
    level, detail = host(tmp_path, compose_stub("dev", wide, "[]"))["exposure"]
    assert level == "red" and "caddy:8080" in detail


def test_host_a3_names_without_values_and_only_in_prod_or_when_asked(tmp_path):
    env = json.dumps(["MONA_ENV=prod", f"OPENROUTER_API_KEY={FIXTURE_KEY}", "HF_TOKEN="])
    out = host(tmp_path, compose_stub("prod", "[]", env))
    level, detail = out["A3"]
    assert level == "red" and "mona-api-1: OPENROUTER_API_KEY" in detail
    assert "HF_TOKEN" not in detail and FIXTURE_KEY not in detail
    clean_env = json.dumps(["MONA_ENV=prod"])
    assert host(tmp_path, compose_stub("prod", "[]", clean_env))["A3"][0] == "green"
    assert "A3" not in host(tmp_path, compose_stub("dev", "[]", env))
    assert host(tmp_path, compose_stub("dev", "[]", env), "--privacy")["A3"][0] == "red"

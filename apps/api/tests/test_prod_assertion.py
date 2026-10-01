"""C9 §8 test 1 (the prod assertion), the `mona.llm` guard (§1.2) and the compose settings."""

import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
import yaml

from mona import llm
from mona.privacy import ProdCheckFailed, llm_endpoint_problem
from mona.settings import Settings

ROOT = Path(__file__).resolve().parents[3]
API = ROOT / "apps" / "api"
MONA = Path(sys.executable).parent / "mona"
FIXTURE_KEY = "sk-or-v1-fixture-value-never-printed"
LOCAL = "http://llama-swap:8080/v1"
PROD_CONFIG = ROOT / "deploy" / "hermes" / "config.prod.yaml"


def run(args: list[str], **env: str) -> subprocess.CompletedProcess:
    base = {
        "PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", "/tmp"),
        "DATABASE_URL": os.environ.get("DATABASE_URL", "postgresql+psycopg://x:y@localhost/z"),
    }  # fmt: skip
    return subprocess.run(
        args, cwd=API, env={**base, **env}, capture_output=True, text=True, timeout=60
    )


def start_api(**env: str) -> subprocess.CompletedProcess:
    return run([sys.executable, "-c", "import mona.app"], **env)


def output(r: subprocess.CompletedProcess) -> str:
    return r.stdout + r.stderr


@pytest.mark.parametrize(
    "args",
    [
        [sys.executable, "-c", "import mona.app"],
        [sys.executable, "-c", "import mona.jobs"],
        [str(MONA), "version"],
    ],
)
def test_nothing_starts_without_mona_env(args):
    r = run(args)
    assert r.returncode != 0 and "MONA_ENV" in output(r)


def test_prod_refuses_a_cloud_key_naming_it_without_its_value():
    r = start_api(MONA_ENV="prod", MONA_LLM_BASE_URL=LOCAL, OPENROUTER_API_KEY=FIXTURE_KEY)
    assert r.returncode != 0
    assert "A1" in output(r) and "OPENROUTER_API_KEY" in output(r)
    assert FIXTURE_KEY not in output(r)


@pytest.mark.parametrize(
    "url", ["https://openrouter.ai/api/v1", "http://8.8.8.8/v1", "https://api.groq.com.evil/v1", ""]
)
def test_prod_refuses_a_model_url_that_is_not_local(url):
    r = start_api(MONA_ENV="prod", MONA_LLM_BASE_URL=url)
    assert r.returncode != 0 and "A2" in output(r) and "MONA_LLM_BASE_URL" in output(r)


def test_prod_starts_with_the_local_endpoint():
    r = start_api(MONA_ENV="prod", MONA_LLM_BASE_URL=LOCAL)
    assert r.returncode == 0, output(r)


def test_dev_may_carry_the_cloud_key():
    assert start_api(MONA_ENV="dev", OPENROUTER_API_KEY=FIXTURE_KEY).returncode == 0


@pytest.mark.parametrize(
    ("host", "addresses", "ok"),
    [
        ("llama-swap", [], True),
        ("llm.lan", ["192.168.1.20"], True),
        ("box.local", ["10.0.0.5", "fd00::1"], True),
        ("mixed.example", ["10.0.0.5", "93.184.216.34"], False),
        ("public.example", ["93.184.216.34"], False),
        ("eu.openrouter.ai", ["10.0.0.1"], False),
        ("nowhere.example", [], False),
    ],
)
def test_the_endpoint_check_is_by_address(host, addresses, ok):
    problem = llm_endpoint_problem(f"http://{host}:8080/v1", resolve=lambda _: addresses)
    assert (problem is None) == ok, problem


# --- `mona check-prod` (A3–A5; the hermes-seed half) ---


def profile(tmp_path: Path, *, env: str = "", config: dict | None = None) -> Path:
    home = tmp_path / "hermes"
    home.mkdir()
    (home / ".env").write_text(env)
    cfg = config if config is not None else yaml.safe_load(PROD_CONFIG.read_text())
    (home / "config.yaml").write_text(yaml.safe_dump(cfg))
    return home


def check(home: Path, **env: str) -> subprocess.CompletedProcess:
    return run(
        [str(MONA), "check-prod", "--hermes-home", str(home)],
        MONA_ENV="prod", MONA_LLM_BASE_URL=LOCAL, MONA_LLM_MODEL="qwen36", **env,
    )  # fmt: skip


def test_the_shipped_prod_profile_passes(tmp_path):
    r = check(profile(tmp_path, env="API_SERVER_KEY=abc\nTELEGRAM_BOT_TOKEN=t\n"))
    assert r.returncode == 0, output(r)
    assert [ln.split()[:2] for ln in r.stdout.splitlines()] == [
        ["A1", "ok"], ["A2", "ok"], ["A4", "ok"], ["A5", "ok"],
    ]  # fmt: skip


@pytest.mark.parametrize("line", [f"OPENROUTER_API_KEY={FIXTURE_KEY}",
                                  f"export HF_TOKEN='{FIXTURE_KEY}'"])  # fmt: skip
def test_a_cloud_key_in_the_profile_env_fails_a4(tmp_path, line):
    r = check(profile(tmp_path, env=f"# keys\n{line}\n"))
    assert r.returncode == 1
    assert "A4 FAILED" in r.stdout and line.split("=")[0].split()[-1] in r.stdout
    assert FIXTURE_KEY not in output(r)


def test_an_empty_cloud_key_in_the_profile_env_passes(tmp_path):
    assert check(profile(tmp_path, env="OPENROUTER_API_KEY=\n")).returncode == 0


@pytest.mark.parametrize(
    ("change", "says"),
    [
        (lambda c: c["model"].update(provider="openrouter"), "model.provider"),
        (lambda c: c["model"].update(base_url="https://openrouter.ai/api/v1"), "model.base_url"),
        (lambda c: c["agent"]["disabled_toolsets"].remove("terminal"), "lacks terminal"),
        (lambda c: c["agent"]["disabled_toolsets"].append("mona"), "names mona"),
        (lambda c: c["platform_toolsets"].update(cron=["memory", "mona_tg"]), "platform_toolsets"),
        (lambda c: c["auxiliary"]["vision"].update(provider="openrouter"), "auxiliary.vision"),
        (lambda c: c.update(provider_routing={"only": ["x"]}), "provider_routing"),
        (lambda c: c["telemetry"]["shared_metrics"].update(enabled=True), "telemetry"),
        (lambda c: c["mcp_servers"]["mona_tg"]["headers"].update({"X-Mona-Channel": "web"}),
         "mcp_servers.mona_tg"),
    ],
)  # fmt: skip
def test_a_config_off_the_lockdown_fails_a5(tmp_path, change, says):
    cfg = yaml.safe_load(PROD_CONFIG.read_text())
    change(cfg)
    r = check(profile(tmp_path, config=cfg))
    assert r.returncode == 1 and "A5 FAILED" in r.stdout and says in r.stdout


def test_a3_reads_the_rendered_compose_by_name(tmp_path):
    rendered = {"services": {
        "api": {"environment": {"MONA_ENV": "prod"}},
        "hermes": {"environment": {"API_SERVER_KEY": "x", "OPENROUTER_API_KEY": FIXTURE_KEY}},
    }}  # fmt: skip
    out = tmp_path / "compose.json"
    out.write_text(json.dumps(rendered))
    r = run([str(MONA), "check-prod", "--compose-json", str(out)], MONA_ENV="prod",
            MONA_LLM_BASE_URL=LOCAL)  # fmt: skip
    assert r.returncode == 1 and "A3 FAILED: hermes: OPENROUTER_API_KEY" in r.stdout
    assert FIXTURE_KEY not in output(r)


# --- the guard for the model client ---


def prod() -> Settings:
    return Settings(database_url="postgresql+psycopg://x:y@h/d", mona_env="prod",
                    mona_llm_base_url=LOCAL)  # fmt: skip


async def test_the_guarded_client_refuses_any_other_host_before_connecting():
    seen: list[str] = []
    transport = httpx.MockTransport(lambda r: seen.append(str(r.url)) or httpx.Response(200))
    async with llm.guarded_http_client(prod(), transport=transport) as client:
        assert (await client.post(f"{LOCAL}/chat/completions")).status_code == 200
        for url in ("https://openrouter.ai/api/v1/chat/completions",
                    "http://llama-swap:9090/v1/chat/completions"):  # fmt: skip
            with pytest.raises(ProdCheckFailed):
                await client.post(url)
    assert seen == [f"{LOCAL}/chat/completions"]


async def test_dev_goes_to_openrouter_unless_a_local_url_is_set():
    dev = Settings(database_url="postgresql+psycopg://x:y@h/d", mona_env="dev")
    assert llm.endpoint(dev) == llm.ModelEndpoint("https://openrouter.ai/api/v1", False)
    transport = httpx.MockTransport(lambda r: httpx.Response(200))
    async with llm.guarded_http_client(dev, transport=transport) as client:
        assert (await client.get("https://openrouter.ai/api/v1/models")).status_code == 200
    with pytest.raises(ProdCheckFailed):
        llm.endpoint(Settings(database_url="postgresql+psycopg://x:y@h/d", mona_env="prod",
                              mona_llm_base_url="https://openrouter.ai/api/v1"))  # fmt: skip


def test_the_model_client_refuses_a_cloud_endpoint_in_prod():
    from mona.pipeline.model import LlmClient

    cloud = prod().model_copy(update={"mona_llm_base_url": "https://openrouter.ai/api/v1"})
    with pytest.raises(ProdCheckFailed):
        LlmClient.from_settings(cloud)


def test_the_model_client_sends_only_to_the_local_endpoint_in_prod(monkeypatch):
    from mona.pipeline.model import LlmClient, TransportError

    seen: list[str] = []
    transport = httpx.MockTransport(lambda r: seen.append(str(r.url)) or httpx.Response(500))
    guarded = llm.guarded_http_client
    monkeypatch.setattr(llm, "guarded_http_client", lambda s: guarded(s, transport=transport))
    schema = {"type": "object", "properties": {}, "additionalProperties": False}
    client = LlmClient.from_settings(prod())
    with pytest.raises(TransportError):
        client.complete("s", "u", schema)
    assert seen and all(u.startswith(f"{LOCAL}/") for u in seen)
    seen.clear()
    client._chat.client.base_url = "https://openrouter.ai/api/v1"
    with pytest.raises(ProdCheckFailed):
        client.complete("s", "u", schema)
    assert seen == []


def test_the_interview_calls_send_only_to_the_local_endpoint_in_prod(monkeypatch):
    from mona.interviews.llm import from_settings
    from mona.interviews.model import ModelError

    seen: list[str] = []
    transport = httpx.MockTransport(lambda r: seen.append(str(r.url)) or httpx.Response(400))
    guarded = llm.guarded_http_client
    monkeypatch.setattr(llm, "guarded_http_client", lambda s: guarded(s, transport=transport))
    model = from_settings(prod())
    kw = {"temperature": 0, "max_tokens": 10, "timeout_s": 5}
    with pytest.raises(ModelError):
        list(model.stream("s", "u", **kw))
    with pytest.raises(ModelError):
        model.complete_json("s", "u", {"type": "object"}, name="x", **kw)
    assert len(seen) == 2 and all(u.startswith(f"{LOCAL}/") for u in seen)
    seen.clear()
    model.client._chat.client.base_url = "https://openrouter.ai/api/v1"
    with pytest.raises((ModelError, ProdCheckFailed)):
        list(model.stream("s", "u", **kw))
    with pytest.raises((ModelError, ProdCheckFailed)):
        model.complete_json("s", "u", {"type": "object"}, name="x", **kw)
    assert seen == []


# --- compose (C9 §7, A13) ---


def test_compose_logs_tersely_and_mounts_only_the_two_attachment_subtrees():
    services = yaml.safe_load((ROOT / "compose.yaml").read_text())["services"]
    assert "log_error_verbosity=terse" in services["postgres"]["command"]
    mounts = [v for v in services["api"]["volumes"] if isinstance(v, dict)]
    assert [(m["source"], m["target"], m["volume"]["subpath"], m["read_only"]) for m in mounts] == [
        ("hermes_data", "/opt/data/cache/documents", "cache/documents", True),
        ("hermes_data", "/opt/data/cache/images", "cache/images", True),
    ]

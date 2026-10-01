"""C9 §8 test 2 (L6): the rendered prod compose file, the Caddyfile, deploy/bin/deploy."""

import json
import os
import re
import shutil
import socket
import stat
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from mona.privacy import CLOUD_KEYS

ROOT = Path(__file__).resolve().parents[3]
OVERLAY = ROOT / "deploy" / "compose.prod.yaml"
CADDYFILE = ROOT / "deploy" / "caddy" / "Caddyfile"
ENV_EXAMPLE = ROOT / "deploy" / ".env.prod.example"
DEPLOY = ROOT / "deploy" / "bin" / "deploy"
FIXTURE_KEY = "sk-or-v1-fixture-value-never-printed"
PY_SERVICES = ("api", "worker-llm", "worker-cpu", "migrate", "ops", "hermes-seed")
FIXTURE_ENV = {
    "POSTGRES_PASSWORD": "pw", "MONA_SERVICE_KEY": "k" * 32, "HERMES_API_KEY": "h" * 32,
    "MONA_LLM_BASE_URL": "http://llama-swap:8080/v1", "MONA_LLM_MODEL": "qwen3.6-35b-a3b",
    "MONA_PUBLIC_ORIGIN": "http://localhost:8080", "MONA_TAG": "t1",
    "OPENROUTER_API_KEY": FIXTURE_KEY, "HF_TOKEN": FIXTURE_KEY,
}  # fmt: skip

needs_docker = pytest.mark.skipif(shutil.which("docker") is None, reason="docker is not installed")


@pytest.fixture(scope="module")
def rendered(tmp_path_factory) -> dict:
    env_file = tmp_path_factory.mktemp("compose") / "fixture.env"
    env_file.write_text("".join(f"{k}={v}\n" for k, v in FIXTURE_ENV.items()))
    cmd = ["docker", "compose", "--env-file", str(env_file), "-p", "l6test"]
    cmd += [
        "-f",
        "compose.yaml",
        "-f",
        str(OVERLAY),
        "--profile",
        "ops",
        "config",
        "--format",
        "json",
    ]
    out = subprocess.run(
        cmd, cwd=ROOT, capture_output=True, text=True,
        env={"PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", "/tmp")},
    )  # fmt: skip
    assert out.returncode == 0, out.stderr[-500:]
    return json.loads(out.stdout)


def env_of(service: dict) -> dict[str, str]:
    env = service.get("environment") or {}
    return {k: "" if v is None else str(v) for k, v in env.items()}


@needs_docker
def test_every_python_service_runs_as_prod_without_a_cloud_key_name(rendered):
    services = rendered["services"]
    assert set(PY_SERVICES) <= set(services)
    for name in PY_SERVICES:
        assert env_of(services[name]).get("MONA_ENV") == "prod", name
        assert services[name].get("env_file") is None, name
    for name, svc in services.items():
        leaked = [k for k in CLOUD_KEYS if k in env_of(svc)]
        assert not leaked, f"{name}: {leaked}"
    assert FIXTURE_KEY not in json.dumps({n: env_of(s) for n, s in services.items()})


@needs_docker
def test_only_caddy_publishes_a_port_and_only_on_loopback(rendered):
    published = {
        n: [(p.get("host_ip"), p.get("published")) for p in s.get("ports", [])]
        for n, s in rendered["services"].items()
        if s.get("ports")
    }
    assert published == {"caddy": [("127.0.0.1", "8080")]}
    for name in ("api", "hermes", "postgres"):
        assert not rendered["services"][name].get("ports"), name


@needs_docker
def test_nothing_mounts_the_docker_socket_and_the_dev_server_is_gone(rendered):
    for name, svc in rendered["services"].items():
        mounts = [v.get("source", "") for v in svc.get("volumes", [])]
        assert not any("docker.sock" in m for m in mounts), name
        assert not any(m.startswith(str(ROOT / "apps" / "api")) for m in mounts), name
    assert "web" not in rendered["services"]


@needs_docker
def test_the_api_mounts_only_the_two_attachment_subtrees_read_only(rendered):
    vols = rendered["services"]["api"]["volumes"]
    hermes = [v for v in vols if v.get("source") == "hermes_data"]
    assert {(v["target"], v["volume"]["subpath"], v.get("read_only")) for v in hermes} == {
        ("/opt/data/cache/documents", "cache/documents", True),
        ("/opt/data/cache/images", "cache/images", True),
    }


@needs_docker
def test_long_running_services_restart_and_run_as_non_root(rendered):
    services = rendered["services"]
    for name in ("postgres", "api", "worker-llm", "worker-cpu", "hermes", "caddy"):
        assert services[name]["restart"] == "unless-stopped", name
    for name in ("api", "worker-llm", "worker-cpu", "migrate", "caddy"):
        uid = services[name]["user"].split(":")[0]
        assert uid not in ("0", "root"), name
    assert env_of(services["hermes"])["HERMES_UID"] == "1000"
    assert (
        services["hermes"]["depends_on"]["hermes-seed"]["condition"]
        == "service_completed_successfully"
    )


@needs_docker
def test_the_hermes_container_gets_the_local_endpoint_and_no_provider_key(rendered):
    env = env_of(rendered["services"]["hermes"])
    assert env["MONA_LLM_BASE_URL"] == FIXTURE_ENV["MONA_LLM_BASE_URL"]
    assert {"API_SERVER_KEY", "MONA_SERVICE_KEY", "MONA_LLM_MODEL"} <= set(env)
    assert not set(CLOUD_KEYS) & set(env)


@needs_docker
def test_a3_passes_on_the_rendered_file(rendered, tmp_path):
    out = tmp_path / "compose.json"
    out.write_text(json.dumps(rendered))
    mona = Path(sys.executable).parent / "mona"
    env = {
        "PATH": os.environ["PATH"], "MONA_ENV": "prod", "HOME": "/tmp",
        "MONA_LLM_BASE_URL": FIXTURE_ENV["MONA_LLM_BASE_URL"],
    }  # fmt: skip
    r = subprocess.run(
        [str(mona), "check-prod", "--compose-json", str(out)],
        env=env,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0 and "A3 ok" in r.stdout, r.stdout + r.stderr


def test_every_required_variable_is_listed_in_the_env_example():
    required = set(re.findall(r"\$\{([A-Z_]+):\?", OVERLAY.read_text()))
    listed = {
        line.split("=")[0]
        for line in ENV_EXAMPLE.read_text().splitlines()
        if re.match(r"[A-Z_]+=", line)
    }
    assert required - {"MONA_TAG"} <= listed, required - listed
    assert not set(CLOUD_KEYS) & listed


def test_the_env_example_holds_no_values():
    for line in ENV_EXAMPLE.read_text().splitlines():
        if re.match(r"[A-Z_]+=", line):
            assert line.split("=", 1)[1] == "", line


# --- the Caddyfile, run in a container against a stub api that reads every body ---

CAP = 250 * 1024 * 1024
SEEN: list[tuple[str, int]] = []


class Api(BaseHTTPRequestHandler):
    def _read(self) -> int:
        n = 0
        if self.headers.get("transfer-encoding") == "chunked":
            while size := int(self.rfile.readline().strip() or b"0", 16):
                n += len(self.rfile.read(size))
                self.rfile.readline()
        else:
            left = int(self.headers.get("content-length") or 0)
            while left > 0 and (chunk := self.rfile.read(min(left, 1 << 20))):
                n += len(chunk)
                left -= len(chunk)
        return n

    def reply(self, code: int) -> None:
        body = b"api"
        try:
            self.send_response(code)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except OSError:
            pass

    def do_GET(self) -> None:
        SEEN.append((self.path, 0))
        self.reply(200)

    def do_POST(self) -> None:
        SEEN.append((self.path, self._read()))
        self.reply(200)

    do_PATCH = do_POST

    def log_message(self, *a) -> None:
        pass


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def caddy(tmp_path_factory):
    if shutil.which("docker") is None:
        pytest.skip("docker is not installed")
    image = "caddy:2-alpine"
    if subprocess.run(["docker", "image", "inspect", image], capture_output=True).returncode != 0:
        if subprocess.run(["docker", "pull", image], capture_output=True).returncode != 0:
            pytest.skip("caddy:2-alpine is not available")
    api = ThreadingHTTPServer(("127.0.0.1", free_port()), Api)
    threading.Thread(target=api.serve_forever, daemon=True).start()
    port = free_port()
    work = tmp_path_factory.mktemp("caddy")
    (work / "srv").mkdir()
    (work / "srv" / "index.html").write_text("spa")
    (work / "srv" / "app.js").write_text("js")
    text = CADDYFILE.read_text().replace(":8080 {", f"http://127.0.0.1:{port} {{", 1)
    (work / "Caddyfile").write_text(text.replace("api:8765", f"127.0.0.1:{api.server_port}"))
    name = f"l6-caddy-test-{port}"
    subprocess.run(
        ["docker", "run", "--rm", "-d", "--name", name, "--network", "host",
         "-v", f"{work / 'Caddyfile'}:/etc/caddy/Caddyfile:ro", "-v", f"{work / 'srv'}:/srv:ro",
         image],
        check=True, capture_output=True,
    )  # fmt: skip
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            with socket.socket() as s:
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    break
            time.sleep(0.2)
        yield f"http://127.0.0.1:{port}"
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)
        api.shutdown()


def curl(url: str, *args: str) -> str:
    out = subprocess.run(
        ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", *args, url],
        capture_output=True, text=True, timeout=120,
    )  # fmt: skip
    return out.stdout


def test_mcp_is_never_proxied(caddy):
    SEEN.clear()
    assert curl(f"{caddy}/mcp") == "404"
    assert curl(f"{caddy}/mcp/x") == "404"
    assert curl(f"{caddy}/mcp/", "-X", "POST", "-d", "{}") == "404"
    assert not [p for p, _ in SEEN if p.startswith("/mcp")]


def test_api_is_proxied_and_the_web_build_is_served_with_a_spa_fallback(caddy):
    SEEN.clear()
    assert curl(f"{caddy}/api/health") == "200" and SEEN == [("/api/health", 0)]
    assert curl(f"{caddy}/app.js") == "200"
    assert curl(f"{caddy}/some/client/route") == "200"
    body = subprocess.run(
        ["curl", "-s", f"{caddy}/some/client/route"], capture_output=True, text=True
    )
    assert body.stdout == "spa"


def test_a_300_mb_body_on_intake_is_refused_and_never_fully_forwarded(caddy):
    SEEN.clear()
    chunks = "head -c 314572800 /dev/zero"
    code = subprocess.run(
        f"{chunks} | curl -s -o /dev/null -w '%{{http_code}}' -X POST -T - {caddy}/api/intake",
        shell=True, capture_output=True, text=True, timeout=120,
    ).stdout  # fmt: skip
    assert code == "413"
    assert all(n <= CAP for _, n in SEEN)


def test_other_api_paths_cap_the_body_at_64_kb(caddy):
    SEEN.clear()
    ok = subprocess.run(
        f"head -c 60000 /dev/zero | curl -s -o /dev/null -w '%{{http_code}}' -X PATCH -T - "
        f"{caddy}/api/settings",
        shell=True, capture_output=True, text=True, timeout=60,
    ).stdout  # fmt: skip
    big = subprocess.run(
        f"head -c 70000 /dev/zero | curl -s -o /dev/null -w '%{{http_code}}' -X PATCH -T - "
        f"{caddy}/api/settings",
        shell=True, capture_output=True, text=True, timeout=60,
    ).stdout  # fmt: skip
    assert (ok, big) == ("200", "413")


def test_the_caddyfile_proxies_only_the_api_and_logs_nothing():
    text = CADDYFILE.read_text()
    assert text.count("reverse_proxy") == 2 and "reverse_proxy hermes" not in text
    assert "output discard" in text
    assert text.index("@mcp") < text.index("/api/intake") < text.index("/api/*")


# --- deploy/bin/deploy bookkeeping, with a docker stub ---


def deploy_env(tmp_path: Path) -> dict[str, str]:
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    docker = bindir / "docker"
    docker.write_text(f'#!/bin/sh\necho "$*" >> {tmp_path}/calls\n')
    docker.chmod(docker.stat().st_mode | stat.S_IEXEC)
    git = bindir / "git"
    git.write_text("#!/bin/sh\necho abc1234\n")
    git.chmod(git.stat().st_mode | stat.S_IEXEC)
    return {
        "PATH": f"{bindir}:/usr/bin:/bin", "HOME": str(tmp_path), "MONA_ROOT": str(ROOT),
        "MONA_DEPLOY_STATE": str(tmp_path / "state"),
    }  # fmt: skip


def deploy(tmp_path: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(DEPLOY), "--no-doctor", *args],
        env=deploy_env(tmp_path),
        capture_output=True,
        text=True,
    )


def calls(tmp_path: Path) -> list[str]:
    return (tmp_path / "calls").read_text().splitlines()


def test_deploy_keeps_two_releases_and_rolls_back_one(tmp_path):
    for tag in ("a", "b", "c"):
        assert deploy(tmp_path, "--tag", tag).returncode == 0
    state = tmp_path / "state"
    assert (state / "releases").read_text().split() == ["b", "c"]
    assert (state / "current").read_text().strip() == "c"
    removed = [c for c in calls(tmp_path) if c.startswith("rmi")]
    assert removed == ["rmi mona-api:a", "rmi mona-web:a"]
    r = deploy(tmp_path, "--rollback")
    assert r.returncode == 0 and "running release b" in r.stdout
    assert (state / "current").read_text().strip() == "b"
    assert "no earlier release" in deploy(tmp_path, "--rollback").stderr


def test_deploy_without_a_release_refuses_to_roll_back(tmp_path):
    r = deploy(tmp_path, "--rollback")
    assert r.returncode == 1 and "no earlier release" in r.stderr

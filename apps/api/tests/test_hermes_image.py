"""A57 on the pinned Hermes image: the prompt each config renders with no turn passes the prompt
check, and one prod turn through Hermes' API server reaches a capturing model endpoint with the
sampling extras and the cut system prompt."""

import json
import socket
import subprocess
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

from mona import hermes_prompt as hp
from mona.privacy import API_SERVER_HINT, LLM_EXTRA_BODY
from tests.hermes_image import (
    CUT,
    DEV_ENV,
    HERMES,
    PROD_ENV,
    ROOT,
    ensure_image,
    render,
    seed_command,
)

SOUL = HERMES / "SOUL.md"
SOUL_FIRST_LINE = SOUL.read_text().splitlines()[0]
MODEL = "qwen-test"
API_KEY = "a" * 40
PROBE = ROOT / "apps" / "api" / "src" / "mona" / "hermes_prompt.py"


@pytest.mark.parametrize("wsl", [False, True], ids=["linux", "wsl"])
@pytest.mark.parametrize(
    ("config", "env"),
    [("config.yaml", DEV_ENV), ("config.prod.yaml", PROD_ENV)],
    ids=["dev", "prod"],
)
def test_each_config_renders_a_prompt_that_passes_the_check(config, env, wsl):
    out = render(HERMES / config, SOUL, env, wsl)
    prompt = out["prompt"]
    assert "# Hermes runtime environment" in prompt and ("/mnt/c/" in prompt) == wsl
    cut = hp.load_cut(CUT)
    assert hp.surviving_markers(prompt, cut) == []
    assert hp.prompt_line(prompt, cut)[0] == hp.GREEN
    text, _ = cut(prompt)
    assert text.startswith(SOUL_FIRST_LINE) and API_SERVER_HINT in text
    assert out["extra_body"] == (LLM_EXTRA_BODY if config == "config.prod.yaml" else None)


# --- one turn through Hermes, with the prod profile the prod seed installs ---


class Capture(BaseHTTPRequestHandler):
    seen: list[dict] = []

    def _send(self, code: int, body: bytes, kind: str = "application/json") -> None:
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path.rstrip("/").endswith("/models"):
            return self._send(200, json.dumps({"object": "list", "data": [{"id": MODEL}]}).encode())
        self._send(404, b"{}")

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        Capture.seen.append({"path": self.path, "body": body})
        if not self.path.endswith("/chat/completions"):
            return self._send(404, b"{}")
        base = {"id": "c1", "created": 0, "model": MODEL}
        if not body.get("stream"):
            message = {"role": "assistant", "content": "Bonjour."}
            return self._send(200, json.dumps({
                **base, "object": "chat.completion",
                "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }).encode())  # fmt: skip
        chunks = [
            {"choices": [{"index": 0, "delta": {"role": "assistant", "content": "Bonjour."}}]},
            {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
             "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}},
        ]  # fmt: skip
        stream = "".join(
            f"data: {json.dumps({**base, 'object': 'chat.completion.chunk', **c})}\n\n"
            for c in chunks
        )
        self._send(200, (stream + "data: [DONE]\n\n").encode(), "text/event-stream")

    def log_message(self, *a) -> None:
        pass


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def docker(*args: str, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True, **kw)


@pytest.fixture(scope="module")
def turn(tmp_path_factory):
    """Seeds a fresh volume with the prod seed, starts Hermes on it and sends one web turn."""
    image = ensure_image()
    work = tmp_path_factory.mktemp("capture")
    stub = work / "stub"
    stub.mkdir()
    (stub / "mona").write_text("#!/bin/sh\nexit 0\n")
    (stub / "mona").chmod(0o755)
    Capture.seen = []
    upstream = ThreadingHTTPServer(("127.0.0.1", free_port()), Capture)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    name = f"mona-a57-capture-{uuid.uuid4().hex[:8]}"
    port = free_port()
    seeded = docker(
        "run", "--rm", "--network", "none", "-u", "0:0", "-v", f"{HERMES}:/seed:ro",
        "-v", f"{name}:/opt/data", "-v", f"{stub}:/stub:ro", "-e", "PATH=/stub:/usr/bin:/bin",
        "--entrypoint", "sh", image, "-c", seed_command(work, "deploy/compose.prod.yaml"),
    )  # fmt: skip
    assert seeded.returncode == 0, seeded.stderr[-800:]
    env = {
        "HERMES_UID": "1000", "HERMES_GID": "1000", "API_SERVER_KEY": API_KEY,
        "API_SERVER_HOST": "127.0.0.1", "API_SERVER_PORT": str(port),
        "API_SERVER_MODEL_NAME": "mona",
        "MONA_SERVICE_KEY": PROD_ENV["MONA_SERVICE_KEY"], "MONA_LLM_MODEL": MODEL,
        "MONA_LLM_BASE_URL": f"http://127.0.0.1:{upstream.server_port}/v1",
    }  # fmt: skip
    started = docker(
        "run", "-d", "--name", name, "--network", "host", "--add-host", "api:127.0.0.1",
        "-v", f"{name}:/opt/data", *[x for k, v in env.items() for x in ("-e", f"{k}={v}")],
        image, "gateway", "run",
    )  # fmt: skip
    try:
        assert started.returncode == 0, started.stderr[-800:]
        base = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 180
        while True:
            try:
                if httpx.get(f"{base}/health", timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            assert time.monotonic() < deadline, docker("logs", name).stderr[-3000:]
            time.sleep(1)
        reply = httpx.post(
            f"{base}/v1/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}"},
            json={"model": "mona", "messages": [{"role": "user", "content": "Bonjour"}]},
            timeout=180,
        )
        assert reply.status_code == 200, reply.text[-500:]
        probe = docker(
            "exec", "-i", "-u", "hermes", name, "/opt/hermes/.venv/bin/python", "-",
            input=PROBE.read_text(), timeout=120,
        )  # fmt: skip
        yield {"reply": reply.json(), "seen": list(Capture.seen), "probe": hp.parse(probe.stdout)}
    finally:
        docker("rm", "-f", name)
        docker("volume", "rm", "-f", name)
        upstream.shutdown()


def chat_requests(turn) -> list[dict]:
    return [s["body"] for s in turn["seen"] if s["path"].endswith("/chat/completions")]


def system_text(body: dict) -> str:
    content = next(m for m in body["messages"] if m["role"] in ("system", "developer"))["content"]
    if isinstance(content, list):
        return "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return content


def test_the_turn_reaches_the_model_and_comes_back(turn):
    assert chat_requests(turn)
    assert turn["reply"]["choices"][0]["message"]["content"] == "Bonjour."


def test_every_chat_request_carries_the_sampling_extras_and_the_thinking_budget(turn):
    for body in chat_requests(turn):
        assert body["presence_penalty"] == LLM_EXTRA_BODY["presence_penalty"]
        assert body["reasoning_budget_tokens"] == LLM_EXTRA_BODY["reasoning_budget_tokens"]
        assert body["reasoning_budget_message"] == LLM_EXTRA_BODY["reasoning_budget_message"]


def test_the_system_message_is_soul_without_any_a57_marker(turn):
    for body in chat_requests(turn):
        text = system_text(body)
        assert text.startswith(SOUL_FIRST_LINE + "\n")
        assert [m for m in hp.MARKERS if m in text] == []
        assert "Active Hermes profile" not in text and API_SERVER_HINT in text


def test_hermes_reports_the_plugin_loaded_and_the_doctor_probe_passes(turn):
    assert turn["probe"]["plugin"] == (
        "green", "mona_prompt loaded, llm_request middleware registered",
    )  # fmt: skip
    level, detail = turn["probe"]["prompt"]
    assert level == "green" and "runtime-environment" in detail


def test_the_cut_anchors_on_the_pinned_image_s_own_text():
    script = (
        "import json, sys\n"
        "sys.path.insert(0, '/opt/hermes')\n"
        "import agent.prompt_builder as pb\n"
        "print(json.dumps({n: getattr(pb, n) for n in ('HERMES_AGENT_HELP_GUIDANCE',"
        " 'HERMES_AGENT_HELP_GUIDANCE_NO_SKILLS', 'TASK_COMPLETION_GUIDANCE',"
        " 'PARALLEL_TOOL_CALL_GUIDANCE', 'STEER_CHANNEL_NOTE', 'RUNTIME_ENVIRONMENT_HEADING',"
        " 'RUNTIME_ENVIRONMENT_END')} | {'API': pb.PLATFORM_HINTS['api_server']}))\n"
    )
    out = docker(
        "run", "--rm", "-i", "--network", "none", "-e", "PYTHONDONTWRITEBYTECODE=1",
        "--entrypoint", "/opt/hermes/.venv/bin/python", ensure_image(), "-",
        input=script, timeout=120,
    )  # fmt: skip
    assert out.returncode == 0, out.stderr[-1000:]
    image = json.loads(out.stdout.strip().splitlines()[-1])
    module = {}
    exec(compile(CUT.read_text(), str(CUT), "exec"), module)
    assert {
        "HERMES_AGENT_HELP_GUIDANCE": module["HERMES_HELP"],
        "HERMES_AGENT_HELP_GUIDANCE_NO_SKILLS": module["HERMES_HELP_NO_SKILLS"],
        "TASK_COMPLETION_GUIDANCE": module["FINISHING"],
        "PARALLEL_TOOL_CALL_GUIDANCE": module["PARALLEL"],
        "STEER_CHANNEL_NOTE": module["STEERING"],
        "RUNTIME_ENVIRONMENT_HEADING": module["RUNTIME_START"],
        "RUNTIME_ENVIRONMENT_END": module["RUNTIME_END"],
        "API": module["API_SERVER_HINT"],
    } == image

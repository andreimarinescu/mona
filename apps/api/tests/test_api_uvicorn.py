"""Against a real uvicorn: body limits before auth (C2 §17 item 16) and no query in the logs
(C9 §8 test 10, the access-log part)."""

import os
import select
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
import yaml

from mona.api.session import COOKIE
from tests.api_client import new_session, session_headers

ROOT = Path(__file__).resolve().parents[3]
MIB = 1024 * 1024
SECRET_QUERY = "zebracrossingfixture"


def api_flags() -> list[str]:
    """The api's uvicorn flags as compose runs them, minus host, port and reload."""
    command = yaml.safe_load((ROOT / "compose.yaml").read_text())["services"]["api"]["command"]
    words = command.split()
    flags, skip = [], False
    for w in words[2:]:
        if skip:
            skip = False
            continue
        if w in ("--host", "--port", "--reload-dir"):
            skip = True
            continue
        if w != "--reload":
            flags.append(w)
    return flags


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def server(l2_world, tmp_path):
    port = free_port()
    log = tmp_path / "uvicorn.log"
    env = {**os.environ}
    from mona.settings import get_settings

    s = get_settings()
    env.update(DATABASE_URL=s.database_url, MONA_ENV="dev", MONA_DATA_DIR=str(s.mona_data_dir))
    with log.open("wb") as out:
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "tests.guard_app:app", "--host", "127.0.0.1",
             "--port", str(port), *api_flags()],
            cwd=ROOT / "apps" / "api", env=env, stdout=out, stderr=subprocess.STDOUT,
        )  # fmt: skip
        try:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                try:
                    httpx.get(f"http://127.0.0.1:{port}/__read", timeout=1)
                    break
                except httpx.HTTPError:
                    time.sleep(0.2)
            yield port, log
        finally:
            proc.terminate()
            proc.wait(10)


def bytes_read(port: int) -> int:
    return int(httpx.get(f"http://127.0.0.1:{port}/__read").text)


def raw_post(
    port: int, path: str, headers: dict[str, str], chunks: int = 0, method: str = "POST"
) -> int:
    """A request with these headers; a chunked body sends 1 MiB chunks until the server answers or
    `chunks` are sent. Returns the status."""
    sock = socket.create_connection(("127.0.0.1", port), timeout=30)
    head = f"{method} {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
    head += "".join(f"{k}: {v}\r\n" for k, v in headers.items()) + "\r\n"
    sock.sendall(head.encode())
    chunk = b"%x\r\n" % MIB + b"x" * MIB + b"\r\n"
    for _ in range(chunks):
        if select.select([sock], [], [], 0)[0]:
            break
        try:
            sock.sendall(chunk)
        except (BrokenPipeError, ConnectionResetError):
            break
    answer = b""
    while b"\r\n" not in answer:
        part = sock.recv(65536)
        if not part:
            break
        answer += part
    sock.close()
    return int(answer.split(b" ", 2)[1])


def test_compose_runs_the_api_without_the_access_log():
    assert "--no-access-log" in api_flags()


def test_bodies_are_refused_before_auth_reads_them(server):
    port, _ = server
    declared = raw_post(
        port, "/api/intake",
        {"Content-Type": "application/octet-stream", "Content-Length": str(300 * MIB)},
    )  # fmt: skip
    assert bytes_read(port) < MIB and declared in (401, 413)
    chunked = raw_post(
        port, "/api/intake",
        {"Content-Type": "application/octet-stream", "Transfer-Encoding": "chunked"},
        chunks=300,
    )  # fmt: skip
    assert bytes_read(port) < MIB and chunked in (401, 413)


def test_a_chunked_json_body_past_64_kib_is_413_once_past_the_limit(server):
    port, _ = server
    _, token = new_session()
    headers = {
        "Content-Type": "application/json", "Transfer-Encoding": "chunked",
        "Cookie": f"{COOKIE}={token}", **session_headers(token),
    }  # fmt: skip
    status = raw_post(port, "/api/settings", headers, chunks=10, method="PATCH")
    assert bytes_read(port) < MIB and status == 413


def test_a_70_kib_json_body_is_413_before_parsing(server):
    port, _ = server
    _, token = new_session()
    headers = {
        "Content-Type": "application/json", "Content-Length": str(70 * 1024),
        "Cookie": f"{COOKIE}={token}", **session_headers(token),
    }  # fmt: skip
    status = raw_post(port, "/api/auth/heartbeat", headers)
    assert status == 413 and bytes_read(port) == 0


def test_the_log_has_route_templates_and_no_query(server):
    port, log = server
    _, token = new_session()
    with httpx.Client(base_url=f"http://127.0.0.1:{port}", cookies={COOKIE: token}) as c:
        assert c.get("/api/documents", params={"q": SECRET_QUERY}).status_code == 200
        assert c.get("/api/rules", params={"q": SECRET_QUERY}).status_code == 200
    time.sleep(0.3)
    text = log.read_text(errors="replace")
    assert "GET /api/documents 200" in text and "GET /api/rules 200" in text
    assert SECRET_QUERY not in text and token not in text

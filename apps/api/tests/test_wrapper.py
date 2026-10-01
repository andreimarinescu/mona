"""L6 additions to the host wrapper `deploy/bin/mona`: up, stop, status and the box's default."""

import stat
import subprocess
from pathlib import Path

WRAPPER = Path(__file__).resolve().parents[3] / "deploy" / "bin" / "mona"


def run(tmp_path: Path, *args: str, **env: str) -> list[str]:
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    docker = bindir / "docker"
    docker.write_text(f'#!/bin/sh\necho "TAG=$MONA_TAG $*" >> {tmp_path}/calls\n')
    docker.chmod(docker.stat().st_mode | stat.S_IEXEC)
    base = {"PATH": f"{bindir}:/usr/bin:/bin", "HOME": str(tmp_path), "MONA_ROOT": str(tmp_path)}
    (tmp_path / "calls").write_text("")
    subprocess.run([str(WRAPPER), *args], env={**base, **env}, check=True, capture_output=True)
    return (tmp_path / "calls").read_text().splitlines()


def test_up_stop_and_status_drive_the_configured_stack(tmp_path):
    env = {"MONA_COMPOSE": "docker compose -p demo"}
    assert run(tmp_path, "up", **env) == ["TAG= compose -p demo up -d --wait"]
    assert run(tmp_path, "stop", **env) == ["TAG= compose -p demo stop"]
    assert run(tmp_path, "status", **env) == ["TAG= compose -p demo ps"]


def test_once_deployed_the_wrapper_defaults_to_the_prod_stack_at_the_current_release(tmp_path):
    state = tmp_path / ".deploy"
    state.mkdir()
    (state / "current").write_text("20261008-1200\n")
    (call,) = run(tmp_path, "up")
    assert (
        call == "TAG=20261008-1200 compose -f compose.yaml -f deploy/compose.prod.yaml up -d --wait"
    )


def test_without_a_deploy_the_default_stays_the_dev_stack(tmp_path):
    assert run(tmp_path, "up") == ["TAG= compose up -d --wait"]


def test_an_explicit_compose_command_still_gets_the_current_release_tag(tmp_path):
    state = tmp_path / ".deploy"
    state.mkdir()
    (state / "current").write_text("20261008-1200\n")
    (call,) = run(tmp_path, "up", MONA_COMPOSE="docker compose -p demo -f a.yaml")
    assert call == "TAG=20261008-1200 compose -p demo -f a.yaml up -d --wait"

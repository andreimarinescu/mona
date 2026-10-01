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


def stage_build(tmp_path: Path, *args: str, uncovered: int = 0) -> subprocess.CompletedProcess:
    """`mona stage-build` against a fake docker; the first `uncovered` live runs exit 3."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    docker = bindir / "docker"
    docker.write_text(
        "#!/bin/sh\n"
        f'echo "$*" >> {tmp_path}/calls\n'
        'case "$*" in *"ps --format"*) printf "api=healthy\\nhermes=healthy\\n" ;; esac\n'
        'case "$*" in *"--group live"*)\n'
        f'  n=$(grep -c -- "--group live" {tmp_path}/calls)\n'
        f'  [ "$n" -le {uncovered} ] && exit 3 ;;\n'
        "esac\n"
        "exit 0\n"
    )
    docker.chmod(docker.stat().st_mode | stat.S_IEXEC)
    host = tmp_path / "deploy" / "bin" / "doctor-host"
    host.parent.mkdir(parents=True)
    host.write_text("#!/bin/sh\n")
    host.chmod(host.stat().st_mode | stat.S_IEXEC)
    for d in ("corpus", "synthetic"):
        (tmp_path / d).mkdir()
    (tmp_path / "manifest.jsonl").write_text("")
    (tmp_path / "calls").write_text("")
    env = {
        "PATH": f"{bindir}:/usr/bin:/bin", "HOME": str(tmp_path), "MONA_ROOT": str(tmp_path),
        "MONA_COMPOSE": "docker compose -p st", "MONA_SEED_OVERLAY_HOST": "/o.yaml",
        "MONA_CORPUS_DIR": str(tmp_path / "corpus"),
        "MONA_SYNTHETIC_DIR": str(tmp_path / "synthetic"),
        "MONA_CORPUS_MANIFEST": str(tmp_path / "manifest.jsonl"),
    }  # fmt: skip
    return subprocess.run(
        [str(WRAPPER), "stage-build", "--anchor", "2026-10-20", "--yes", *args],
        env=env, capture_output=True, text=True,
    )  # fmt: skip


def steps_of(tmp_path: Path) -> list[str]:
    calls = (tmp_path / "calls").read_text().splitlines()
    return [
        "mona " + c.split(" ops mona ", 1)[1]
        if " ops mona " in c
        else c.removeprefix("compose -p st ")
        for c in calls
        if "ps --format" not in c and "doctor" not in c
    ]


RESET = [
    "mona ops verify --name demo",
    "stop -t 120 worker-llm worker-cpu hermes api",
    "mona ops restore --name demo --anchor 2026-10-20",
    "start api worker-llm worker-cpu hermes",
    "mona ops postcheck --name demo",
]
LIVE = "mona ops stage intake --group live --debrief --timeout 1800"
SNAP = ["stop -t 120 worker-llm worker-cpu hermes"]
START = ["start api worker-llm worker-cpu hermes"]


def test_stage_build_runs_the_c9_build_order(tmp_path):
    """C9 §6.3: demo before the live batch, demo-prefiled after it, then the refreshed cache."""
    assert stage_build(tmp_path, "--early", "8").returncode == 0
    assert steps_of(tmp_path) == [
        "stop -t 120 worker-llm worker-cpu hermes api",
        "mona ops stage clean",
        "mona seed load /seed --tier preseeded",
        *START,
        "mona ops stage intake --group prefiled --settle --timeout 1800",
        "mona ops stage settings --early 8",
        "mona ops stage evidence",
        *SNAP,
        "mona ops snapshot --name demo --findquery /data/stage-build/findquery.json",
        *START,
        *RESET,
        LIVE,
        *SNAP,
        "mona ops snapshot --name demo-prefiled",
        *START,
        "mona ops refresh-textcache --name demo",
        *RESET,
        "mona ops stage cache-check",
    ]
    for c in (tmp_path / "calls").read_text().splitlines():
        assert (f"{tmp_path}/corpus:/stage/corpus:ro" in c) == ("stage intake" in c), c


def test_stage_build_retries_a_debrief_that_leaves_a_candidate_out(tmp_path):
    assert stage_build(tmp_path, uncovered=1).returncode == 0
    steps = steps_of(tmp_path)
    first = steps.index(LIVE)
    assert steps[first : first + 7] == [LIVE, *RESET, LIVE]
    assert steps[-1] == "mona ops stage cache-check"


def test_stage_build_stops_after_its_attempts(tmp_path):
    done = stage_build(tmp_path, "--attempts", "2", uncovered=5)
    assert done.returncode != 0 and "no usable debrief after 2 attempt(s)" in done.stderr
    steps = steps_of(tmp_path)
    assert steps.count(LIVE) == 2 and "mona ops refresh-textcache --name demo" not in steps

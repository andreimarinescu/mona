"""A57 item 5: both `hermes-seed` services install SOUL, the config and the plugin on every start;
memories and sessions stay. Each rendered seed command runs in the pinned Hermes image."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.hermes_image import HERMES, compose_services, ensure_image, seed_command

FILES = ("plugin.yaml", "__init__.py", "cut.py")


def run_seed(command: str, seed: Path, data: Path, stub: Path) -> dict[str, str]:
    """Runs the seed, then reports owner and mode of every installed path; hands `data` back."""
    report = (
        "cd /opt/data && find . -type f -o -type d | sort"
        " | while read p; do stat -c '%u:%g %a %n' \"$p\"; done;"
        f" chown -R {os.getuid()}:{os.getgid()} /opt/data"
    )
    out = subprocess.run(
        ["docker", "run", "--rm", "--network", "none", "-u", "0:0",
         "-v", f"{seed}:/seed:ro", "-v", f"{data}:/opt/data", "-v", f"{stub}:/stub:ro",
         "-e", "PATH=/stub:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
         "--entrypoint", "sh", ensure_image(), "-c", f"{command}\n{report}"],
        capture_output=True, text=True, timeout=120,
    )  # fmt: skip
    assert out.returncode == 0, out.stderr[-1000:]
    stats = {}
    for line in out.stdout.splitlines():
        owner, mode, path = line.split(" ", 2)
        stats[path.removeprefix("./")] = f"{owner} {mode}"
    return stats


@pytest.fixture
def seed(tmp_path: Path) -> Path:
    """The repo's deploy/hermes, plus bytecode a test run could have left next to the plugin."""
    copy = tmp_path / "seed"
    shutil.copytree(HERMES, copy)
    cache = copy / "plugins" / "mona_prompt" / "__pycache__"
    cache.mkdir(exist_ok=True)
    (cache / "cut.cpython-313.pyc").write_bytes(b"stale")
    return copy


@pytest.fixture
def stub(tmp_path: Path) -> Path:
    folder = tmp_path / "stub"
    folder.mkdir()
    mona = folder / "mona"
    mona.write_text('#!/bin/sh\necho "$*" > /opt/data/.check-prod-args\n')
    mona.chmod(0o755)
    return folder


@pytest.mark.parametrize(
    ("overlay", "config", "config_mode"),
    [((), "config.yaml", "644"), (("deploy/compose.prod.yaml",), "config.prod.yaml", "640")],
    ids=["dev", "prod"],
)
def test_the_seed_installs_soul_config_and_plugin_on_every_start(
    tmp_path, seed, stub, overlay, config, config_mode
):
    command = seed_command(tmp_path, *overlay)
    data = tmp_path / "data"
    data.mkdir()
    stats = run_seed(command, seed, data, stub)
    assert (data / "config.yaml").read_bytes() == (HERMES / config).read_bytes()
    assert (data / "SOUL.md").read_bytes() == (HERMES / "SOUL.md").read_bytes()
    assert stats["config.yaml"] == f"1000:1000 {config_mode}"
    assert stats["SOUL.md"] == "1000:1000 644"
    assert stats["plugins"] == stats["plugins/mona_prompt"] == "0:0 755"
    plugin = sorted(p for p in stats if p.startswith("plugins/mona_prompt/"))
    assert plugin == sorted(f"plugins/mona_prompt/{f}" for f in FILES)
    for f in FILES:
        assert stats[f"plugins/mona_prompt/{f}"] == "0:0 644"
        assert (data / "plugins/mona_prompt" / f).read_bytes() == (
            HERMES / "plugins/mona_prompt" / f
        ).read_bytes()

    (data / "SOUL.md").write_text("# an old SOUL\n")
    (data / "config.yaml").write_text("model: {}\n")
    (data / "plugins/mona_prompt/cut.py").write_text("tampered")
    (data / "plugins/mona_prompt/stale.py").write_text("removed")
    (data / "memories" / "MEMORY.md").write_text("the owner prefers French\n")
    (data / "sessions").mkdir()
    (data / "sessions" / "session_1.json").write_text("{}")
    (data / "state.db").write_bytes(b"sqlite")
    stats = run_seed(command, seed, data, stub)
    assert (data / "SOUL.md").read_bytes() == (HERMES / "SOUL.md").read_bytes()
    assert (data / "config.yaml").read_bytes() == (HERMES / config).read_bytes()
    assert sorted(p.name for p in (data / "plugins/mona_prompt").iterdir()) == sorted(FILES)
    assert (data / "plugins/mona_prompt/cut.py").read_bytes() == (
        HERMES / "plugins/mona_prompt/cut.py"
    ).read_bytes()
    assert (data / "memories" / "MEMORY.md").read_text() == "the owner prefers French\n"
    assert (data / "sessions" / "session_1.json").read_text() == "{}"
    assert (data / "state.db").read_bytes() == b"sqlite"
    checked = data / ".check-prod-args"
    assert checked.is_file() == bool(overlay)
    if overlay:
        assert checked.read_text().strip() == "check-prod --hermes-home /opt/data"


@pytest.mark.parametrize("overlay", [(), ("deploy/compose.prod.yaml",)], ids=["dev", "prod"])
def test_hermes_restarts_whenever_its_seed_is_recreated(tmp_path, overlay):
    depends = compose_services(tmp_path, *overlay)["hermes"]["depends_on"]["hermes-seed"]
    assert depends["condition"] == "service_completed_successfully"
    assert depends["restart"] is True


def plugin_mtimes(command: str, seed: Path, volume: str, stub: Path, before: str = "") -> dict:
    folder = "/opt/data/plugins/mona_prompt"
    report = f"stat -c '%.9Y %u:%g %a %n' {folder} {folder}/*"
    out = subprocess.run(
        ["docker", "run", "--rm", "--network", "none", "-u", "0:0",
         "-v", f"{seed}:/seed:ro", "-v", f"{volume}:/opt/data", "-v", f"{stub}:/stub:ro",
         "-e", "PATH=/stub:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
         "--entrypoint", "sh", ensure_image(), "-c", f"{before}\n{command}\n{report}"],
        capture_output=True, text=True, timeout=120,
    )  # fmt: skip
    assert out.returncode == 0, out.stderr[-1000:]
    rows = [line.split(" ", 3) for line in out.stdout.splitlines()]
    return {Path(path).name: (float(mtime), f"{owner} {mode}") for mtime, owner, mode, path in rows}


@pytest.mark.parametrize("overlay", [(), ("deploy/compose.prod.yaml",)], ids=["dev", "prod"])
def test_an_unchanged_plugin_keeps_its_mtime_and_a_changed_one_is_reinstalled(
    tmp_path, seed, stub, overlay
):
    command = seed_command(tmp_path, *overlay)
    volume = f"mona-a57-seed-{tmp_path.name[-24:].lower()}-{os.getpid()}"
    try:
        first = plugin_mtimes(command, seed, volume, stub)
        assert sorted(first) == sorted(["mona_prompt", *FILES])
        assert plugin_mtimes(command, seed, volume, stub) == first

        with (seed / "plugins/mona_prompt/cut.py").open("a") as f:
            f.write("\n")
        changed = plugin_mtimes(command, seed, volume, stub)
        assert changed["cut.py"][0] > first["cut.py"][0]
        assert {n: v[1] for n, v in changed.items()} == {n: v[1] for n, v in first.items()}

        chowned = plugin_mtimes(
            command, seed, volume, stub, "chown 1000:1000 /opt/data/plugins/mona_prompt/plugin.yaml"
        )
        assert chowned["plugin.yaml"][1] == "0:0 644"
        assert chowned["plugin.yaml"][0] > changed["plugin.yaml"][0]

        for drift, name in (
            ("chmod 666 /opt/data/plugins/mona_prompt/cut.py", "cut.py"),
            ("chmod 777 /opt/data/plugins/mona_prompt", "mona_prompt"),
        ):
            before = plugin_mtimes(command, seed, volume, stub)
            drifted = plugin_mtimes(command, seed, volume, stub, drift)
            assert {n: v[1] for n, v in drifted.items()} == {n: v[1] for n, v in first.items()}
            assert drifted[name][0] > before[name][0], drift
    finally:
        subprocess.run(["docker", "volume", "rm", "-f", volume], capture_output=True)

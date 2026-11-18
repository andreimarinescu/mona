"""The pinned Hermes image for the A57 tests: pulled when missing, never skipped.

Regenerate the prompt fixtures (from apps/api): uv run python -m tests.hermes_image <before-rev>"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
HERMES = ROOT / "deploy" / "hermes"
IMAGE = yaml.safe_load((ROOT / "compose.yaml").read_text())["services"]["hermes"]["image"]
RENDER = Path(__file__).parent / "hermes_render.py"
PROMPTS = Path(__file__).parent / "fixtures" / "hermes" / "prompts"
CUT = HERMES / "plugins" / "mona_prompt" / "cut.py"
SERVICE_KEY = "s" * 32
DEV_ENV = {
    "MONA_CHAT_MODEL": "qwen/qwen3.6-35b-a3b",
    "OPENROUTER_API_KEY": "render-only",
    "MONA_SERVICE_KEY": SERVICE_KEY,
}
PROD_ENV = {
    "MONA_LLM_BASE_URL": "http://10.0.0.5:9292/v1",
    "MONA_LLM_MODEL": "qwen-test",
    "MONA_SERVICE_KEY": SERVICE_KEY,
}
COMPOSE_ENV = {
    "POSTGRES_PASSWORD": "pw", "MONA_SERVICE_KEY": "k" * 32, "HERMES_API_KEY": "h" * 32,
    "OPENROUTER_API_KEY": "or", "MONA_LLM_BASE_URL": "http://llama-swap:8080/v1",
    "MONA_LLM_MODEL": "qwen-test", "MONA_PUBLIC_ORIGIN": "http://localhost:8080", "MONA_TAG": "t1",
}  # fmt: skip
FIXTURE_SOUL = "# Mona\n\nA fixture SOUL; the real one is deploy/hermes/SOUL.md.\n"


def ensure_image() -> str:
    assert shutil.which("docker"), "docker is required for the Hermes image tests"
    if subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True).returncode:
        pulled = subprocess.run(["docker", "pull", IMAGE], capture_output=True, text=True)
        assert pulled.returncode == 0, f"cannot pull {IMAGE}: {pulled.stderr[-300:]}"
    return IMAGE


def render(config: Path, soul: Path, env: dict[str, str], wsl: bool = False) -> dict:
    """No network: the dev config's OpenRouter is unreachable, and no turn is sent."""
    cmd = ["docker", "run", "--rm", "-i", "--network", "none", "--tmpfs", "/opt/data",
           "-v", f"{config}:/in/config.yaml:ro", "-v", f"{soul}:/in/SOUL.md:ro",
           "--entrypoint", "/opt/hermes/.venv/bin/python"]  # fmt: skip
    for k, v in {**env, **({"RENDER_WSL": "1"} if wsl else {})}.items():
        cmd += ["-e", f"{k}={v}"]
    out = subprocess.run(
        [*cmd, ensure_image(), "-"], input=RENDER.read_text(), capture_output=True, text=True,
        timeout=180,
    )  # fmt: skip
    assert out.returncode == 0, out.stderr[-2000:]
    return json.loads(out.stdout.strip().splitlines()[-1])


def compose_services(tmp_path: Path, *overlay: str) -> dict:
    env_file = tmp_path / "fixture.env"
    env_file.write_text("".join(f"{k}={v}\n" for k, v in COMPOSE_ENV.items()))
    cmd = ["docker", "compose", "--env-file", str(env_file), "-p", "seedtest", "-f", "compose.yaml"]
    for f in overlay:
        cmd += ["-f", f]
    out = subprocess.run(
        [*cmd, "config", "--format", "json"], cwd=ROOT, capture_output=True, text=True,
        env={"PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", "/tmp")},
    )  # fmt: skip
    assert out.returncode == 0, out.stderr[-500:]
    return json.loads(out.stdout)["services"]


def seed_command(tmp_path: Path, *overlay: str) -> str:
    """The rendered `hermes-seed` command, with `$$` unescaped as compose does when it runs it."""
    seed = compose_services(tmp_path, *overlay)["hermes-seed"]
    assert seed["entrypoint"] == ["sh", "-c"]
    return seed["command"][0].replace("$$", "$")


def write_fixtures(before_rev: str, work: Path) -> None:
    soul = work / "SOUL.md"
    soul.write_text(FIXTURE_SOUL)
    configs = {"": HERMES}
    before = work / "before"
    before.mkdir()
    for name in ("config.yaml", "config.prod.yaml"):
        text = subprocess.run(
            ["git", "show", f"{before_rev}:deploy/hermes/{name}"], cwd=ROOT,
            capture_output=True, text=True, check=True,
        ).stdout  # fmt: skip
        (before / name).write_text(text)
    configs["before-"] = before
    PROMPTS.mkdir(parents=True, exist_ok=True)
    for prefix, folder in configs.items():
        for kind, file, env, backend in (
            ("prod", "config.prod.yaml", PROD_ENV, "docker"),
            ("dev", "config.yaml", DEV_ENV, "local"),
        ):
            for wsl in (False, True):
                name = f"{prefix}{kind}-{backend}{'-wsl' if wsl else ''}.txt"
                (PROMPTS / name).write_text(render(folder / file, soul, env, wsl)["prompt"])


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        write_fixtures(sys.argv[1], Path(tmp))

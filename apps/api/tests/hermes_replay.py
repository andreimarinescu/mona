"""The pinned Hermes image for the chat-replay tests: the request it builds and the config its
boot migration writes. Regenerate the migrated fixture (from apps/api):
uv run python -m tests.hermes_replay"""

import json
import subprocess
from pathlib import Path

import yaml

from tests.hermes_image import HERMES, ensure_image

PROBE = Path(__file__).parent / "hermes_request.py"
MIGRATED = Path(__file__).parent / "fixtures" / "hermes" / "config.prod.migrated.yaml"
PYTHON = "/opt/hermes/.venv/bin/python"
MIGRATE = (
    "cp /in/config.yaml /opt/data/config.yaml && cd /opt/hermes && "
    f"PYTHONPATH=/opt/hermes {PYTHON} scripts/docker_config_migrate.py >&2 && "
    "cat /opt/data/config.yaml"
)


def _run(config: Path, env: dict[str, str], entrypoint: str, *args: str, stdin: str = "") -> str:
    cmd = ["docker", "run", "--rm", "-i", "--network", "none", "--tmpfs", "/opt/data",
           "-e", "PYTHONDONTWRITEBYTECODE=1", "-v", f"{config}:/in/config.yaml:ro",
           "-v", f"{PROBE}:/in/probe.py:ro", "--entrypoint", entrypoint]  # fmt: skip
    for k, v in env.items():
        cmd += ["-e", f"{k}={v}"]
    out = subprocess.run(
        [*cmd, ensure_image(), *args], input=stdin, capture_output=True, text=True, timeout=180
    )
    assert out.returncode == 0, out.stderr[-2000:]
    return out.stdout


def request_kwargs(config: Path, env: dict[str, str], tools: list[dict]) -> dict:
    """`tools`: MCP tools as the server lists them ({name, description, inputSchema})."""
    stdout = _run(config, env, PYTHON, "/in/probe.py", stdin=json.dumps({"tools": tools}))
    return json.loads(stdout.strip().splitlines()[-1])


def migrated(config: Path) -> dict:
    return yaml.safe_load(_run(config, {}, "sh", "-c", MIGRATE))


if __name__ == "__main__":
    MIGRATED.write_text(yaml.safe_dump(migrated(HERMES / "config.prod.yaml"), sort_keys=False))

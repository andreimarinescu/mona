"""The Hermes profile part of a snapshot (C9 §6.1, §6.5) and what reset installs around it."""

import json
import os
import shutil
import sqlite3
from pathlib import Path

from mona.demo.tools import OpsError, empty_dir, mirror

ATTACHMENT_DIRS = ("cache/documents", "cache/images")
INSTALLED = ("/config.yaml", "/.env", "/cron/")
CLOUD_KEYS = ("OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY")
# Written by Hermes at start or by its scheduler; excluded from the idempotency comparison.
RUNTIME = (
    "cron/jobs.json", "cron/executions.db", "cron/ticker_heartbeat", "cron/ticker_last_success",
    "logs", "sessions",
    "cache", "lazy-packages", "bin", "backups", "home", "state", "platforms", "workspace",
    "audio_cache", "image_cache", "pending_messages", "plans", "pairing", "hooks", "kanban",
    "skins", ".local", "auth.json", "auth.lock", "install_id", ".install_id.lock",
    ".mcp-discovery.lock", "channel_directory.json", "gateway-starts.log", "gateway.lock",
    "gateway.pid", "gateway.sock", "gateway_state.json", "kanban.db", "shared-state.db",
    "response_store.db", "runs_idempotency.db", ".bash_logout", ".bashrc", ".profile",
    "skills/.bundled_manifest",
)  # fmt: skip


def snapshot_part(hermes: Path, dst: Path) -> None:
    """Copy SOUL.md, memories/, skills/ and state.db; create the two empty attachment folders."""
    dst.mkdir(parents=True, exist_ok=True)
    if (hermes / "SOUL.md").is_file():
        shutil.copy2(hermes / "SOUL.md", dst / "SOUL.md")
    for d in ("memories", "skills"):
        if (hermes / d).is_dir():
            mirror(hermes / d, dst / d, "*.lock", ".*.tmp")
    if (hermes / "state.db").is_file():
        src = sqlite3.connect(hermes / "state.db")
        out = sqlite3.connect(dst / "state.db")
        try:
            with out:
                src.backup(out)
            out.execute("PRAGMA journal_mode=DELETE")
        finally:
            out.close()
            src.close()
    for d in ATTACHMENT_DIRS:
        (dst / d).mkdir(parents=True, exist_ok=True)


def restore_part(src: Path, hermes: Path) -> None:
    """`rsync -a --delete` into the profile, except what §6.3 step 5 installs."""
    mirror(src, hermes, *INSTALLED)
    for d in ATTACHMENT_DIRS:
        (hermes / d).mkdir(parents=True, exist_ok=True)


def job_ids(hermes: Path) -> list[str]:
    path = hermes / "cron" / "jobs.json"
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    jobs = data.get("jobs", []) if isinstance(data, dict) else data
    return sorted(str(j["id"]) for j in jobs)


def reset_cron(hermes: Path) -> list[str]:
    """Empty cron/ (past outputs, deliveries, run history) but keep the installed job list."""
    cron = hermes / "cron"
    jobs = cron / "jobs.json"
    kept = jobs.read_bytes() if jobs.is_file() else None
    empty_dir(cron)
    if kept is not None:
        jobs.write_bytes(kept)
        os.chmod(jobs, 0o600)
    return job_ids(hermes)


def install_config(hermes: Path, seed: Path | None, env: str, env_keys: tuple[str, ...]) -> None:
    """§6.5: this environment's config.yaml and a `.env` holding only `env_keys`."""
    if seed is None:
        raise OpsError("MONA_HERMES_SEED is not set: no Hermes config to install")
    src = seed / ("config.prod.yaml" if env == "prod" else "config.yaml")
    if not src.is_file():
        raise OpsError(f"{src.name} is missing from the Hermes seed directory")
    target = hermes / "config.yaml"
    shutil.copyfile(src, target)
    os.chmod(target, 0o640)
    if env == "prod" and (bad := [k for k in env_keys if k in CLOUD_KEYS]):
        raise OpsError(f"prod Hermes .env may not hold {', '.join(bad)}")
    lines = [f"{k}={os.environ[k]}\n" for k in env_keys if k in os.environ]
    env_file = hermes / ".env"
    env_file.write_text("".join(lines), encoding="utf-8")
    os.chmod(env_file, 0o600)

"""Digests that two resets with the same snapshot and anchor must share (C9 §6.3, plan §14)."""

import hashlib
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from psycopg.conninfo import conninfo_to_dict

from mona.demo.hermes import RUNTIME
from mona.demo.snapshot import TREES
from mona.demo.tools import OpsEnv, OpsError, pg_bin, tree_hashes


def normalised_dump(conninfo: str) -> str:
    """Plain whole-database dump without session or queue rows; `\\restrict` lines and comments
    dropped (the token is random per dump)."""
    p = conninfo_to_dict(conninfo)
    env = {**os.environ, "PGPASSWORD": str(p.get("password") or "")}
    cmd = [
        pg_bin("pg_dump"), "--no-owner", "--no-privileges",
        "-h", str(p.get("host", "localhost")), "-p", str(p.get("port", 5432)),
        "-U", str(p["user"]), "-d", str(p["dbname"]),
        "--exclude-table-data=auth_sessions", "--exclude-table-data=procrastinate_*",
    ]  # fmt: skip
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if proc.returncode != 0:
        raise OpsError(f"pg_dump failed ({proc.returncode})")
    keep = [
        line
        for line in proc.stdout.splitlines()
        if not line.startswith("--") and not re.match(r"\\(un)?restrict ", line)
    ]
    return "\n".join(keep) + "\n"


def _digest(hashes: dict[str, str]) -> str:
    h = hashlib.sha256()
    for rel, d in sorted(hashes.items()):
        h.update(f"{d}  {rel}\n".encode())
    return h.hexdigest()


def fingerprint(env: OpsEnv, hermes_only: bool = False, files: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if not hermes_only:
        out["db"] = hashlib.sha256(normalised_dump(env.conninfo).encode()).hexdigest()
        for tree in (*TREES, "exports"):
            hashes = tree_hashes(env.data / tree) if (env.data / tree).is_dir() else {}
            out[tree] = {"files": len(hashes), "sha256": _digest(hashes)}
    if env.hermes is not None:
        hashes = tree_hashes(env.hermes, skip=RUNTIME + _wal(env.hermes))
        out["hermes"] = {"files": len(hashes), "sha256": _digest(hashes)}
        if files:
            out["hermes_files"] = tree_hashes(env.hermes)
    return out


def _wal(home: Path) -> tuple[str, ...]:
    return tuple(
        p.relative_to(home).as_posix()
        for p in home.rglob("*")
        if p.name.endswith(("-wal", "-shm", ".lock", ".pid"))
    )

"""The ops environment and the external tools the snapshot steps run (pg_dump, rsync)."""

import hashlib
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from psycopg.conninfo import conninfo_to_dict

from mona.migrate import libpq
from mona.settings import Settings


class OpsError(Exception):
    """A refused or failed ops step; the message names the check, never document content."""


@dataclass(frozen=True)
class OpsEnv:
    url: str
    data: Path
    hermes: Path | None = None
    hermes_seed: Path | None = None
    env: str = "dev"
    hermes_env_keys: tuple[str, ...] = ()
    data_owner: tuple[int, int] | None = None
    hermes_owner: tuple[int, int] | None = None

    @property
    def conninfo(self) -> str:
        return libpq(self.url)

    @property
    def snapshots(self) -> Path:
        return self.data / "snapshots"

    def snapshot(self, name: str) -> Path:
        if not name or "/" in name or name.startswith("."):
            raise OpsError(f"invalid snapshot name: {name!r}")
        return self.snapshots / name

    @classmethod
    def from_settings(cls, s: Settings) -> "OpsEnv":
        def pair(a: int | None, b: int | None) -> tuple[int, int] | None:
            return (a, b) if a is not None and b is not None else None

        return cls(
            url=s.database_url,
            data=s.mona_data_dir,
            hermes=s.mona_hermes_home,
            hermes_seed=s.mona_hermes_seed,
            env=s.mona_env,
            hermes_env_keys=tuple(k for k in s.mona_hermes_env_keys.split(",") if k.strip()),
            data_owner=pair(s.mona_uid, s.mona_gid),
            hermes_owner=pair(s.hermes_uid, s.hermes_gid),
        )


def pg_bin(name: str) -> str:
    if d := os.environ.get("MONA_PG_BIN"):
        return str(Path(d) / name)
    if dump := os.environ.get("PG_DUMP"):
        sibling = Path(dump).with_name(name)
        if sibling.exists():
            return str(sibling)
    exe = shutil.which(name)
    if not exe:
        raise OpsError(f"{name} not found (PostgreSQL 17 client)")
    return exe


def pg_run(tool: str, conninfo: str, *args: str) -> None:
    p = conninfo_to_dict(conninfo)
    env = {**os.environ, "PGPASSWORD": str(p.get("password") or "")}
    conn = ["-h", str(p.get("host", "localhost")), "-p", str(p.get("port", 5432))]
    conn += ["-U", str(p["user"]), "-d", str(p["dbname"])]
    proc = subprocess.run([pg_bin(tool), *conn, *args], env=env, capture_output=True, text=True)
    if proc.returncode != 0:
        first = next((ln for ln in proc.stderr.splitlines() if "error" in ln.lower()), "")
        raise OpsError(f"{tool} failed ({proc.returncode}): {first.split('DETAIL')[0][:200]}")


def mirror(src: Path, dst: Path, *excludes: str) -> None:
    """`rsync -a --delete src/ dst/`; excluded paths are neither copied nor deleted."""
    dst.mkdir(parents=True, exist_ok=True)
    # --checksum: a file rewritten within the same second at the same size must still be copied.
    cmd = ["rsync", "-a", "--checksum", "--delete", *(f"--exclude={e}" for e in excludes)]
    cmd += [f"{src}/", f"{dst}/"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise OpsError(f"rsync failed ({proc.returncode}): {proc.stderr.strip()[-400:]}")


def empty_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for child in path.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()


def sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def files_under(root: Path) -> list[str]:
    """Every regular file under `root`, as sorted POSIX paths relative to it."""
    out = []
    for dirpath, _, names in os.walk(root):
        for n in names:
            p = Path(dirpath) / n
            if p.is_file() and not p.is_symlink():
                out.append(p.relative_to(root).as_posix())
    return sorted(out)


def tree_hashes(root: Path, skip: tuple[str, ...] = ()) -> dict[str, str]:
    out = {}
    for rel in files_under(root):
        if any(rel == s or rel.startswith(s.rstrip("/") + "/") for s in skip):
            continue
        try:
            out[rel] = sha256_path(root / rel)
        except FileNotFoundError:
            continue
    return out


def chown_tree(path: Path, owner: tuple[int, int] | None) -> None:
    if owner is None or os.geteuid() != 0 or not path.exists():
        return
    uid, gid = owner
    os.lchown(path, uid, gid)
    for dirpath, dirs, names in os.walk(path):
        for n in (*dirs, *names):
            os.lchown(Path(dirpath) / n, uid, gid)

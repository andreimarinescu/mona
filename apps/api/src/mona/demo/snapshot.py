"""C9 §6.1–§6.3: take a snapshot, refresh its text cache, and restore it (`demo-reset`)."""

import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import psycopg
from sqlalchemy import Engine, create_engine, text

from mona import __version__
from mona.demo import anchor, checks, hermes, memory
from mona.demo.tools import (
    OpsEnv,
    OpsError,
    chown_tree,
    empty_dir,
    files_under,
    mirror,
    pg_run,
    sha256_path,
)
from mona.fileops import Roots
from mona.migrate import head_revision, migrate

TREES = ("inbox", "archive", "trash", "textcache", "config")
EXCLUDE_DATA = ("--exclude-table-data=auth_sessions", "--exclude-table-data=procrastinate_*")
FINDQUERY = "findquery.json"


@dataclass
class Report:
    lines: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    def say(self, line: str) -> None:
        self.lines.append(line)


def _engine(env: OpsEnv) -> Engine:
    return create_engine(env.url, connect_args={"connect_timeout": 5})


def _own(env: OpsEnv, *paths: Path) -> None:
    if env.data_owner is not None and os.geteuid() == 0:
        for p in paths:
            os.chown(p, *env.data_owner)


def recover(env: OpsEnv, engine: Engine) -> dict[int, str]:
    """C7 §4.3 recovery, run before a snapshot is taken or restored."""
    from mona.pipeline.hooks import interview_hooks
    from mona.pipeline.stages import recover as run
    from mona.services import make_context

    with engine.connect() as conn:
        if conn.execute(text("SELECT to_regclass('public.file_ops')")).scalar() is None:
            return {}
    return run(make_context(engine, env.data, **interview_hooks()), timedelta(0))


def snapshot_problems(env: OpsEnv, engine: Engine, name: str) -> list[str]:
    """§6.2 items 1–6 and 8 against the live state."""
    with engine.connect() as conn:
        out = checks.db_problems(conn)
        out += checks.tree_problems(conn, Roots.at(env.data))
        if name in checks.STAGE_NAMES:
            out += checks.stage_problems(conn)
    if env.hermes is not None:
        out += checks.hermes_problems(env.hermes)
    return out


def _counts(engine: Engine) -> dict[str, int]:
    tables = {"documents": "documents", "rules": "rules", "batches": "batches",
              "journal_entries": "file_ops"}  # fmt: skip
    with engine.connect() as conn:
        return {k: conn.execute(text(f"SELECT count(*) FROM {t}")).scalar_one()
                for k, t in tables.items()}  # fmt: skip


def _prompt_versions() -> dict[str, str | None]:
    from mona.pipeline.schema import PROMPT_VERSION

    try:
        import mona.interviews as interviews

        c6 = getattr(interviews, "PROMPT_VERSION", None)
    except ImportError:
        c6 = None
    return {"c5": PROMPT_VERSION, "c6": c6}


def write_sums(snap: Path) -> None:
    lines = [
        f"{sha256_path(snap / rel)}  {rel}\n"
        for rel in files_under(snap)
        if rel not in ("sha256sums", "manifest.json")
    ]
    tmp = snap / ".sha256sums.tmp"
    tmp.write_text("".join(lines), encoding="utf-8")
    os.replace(tmp, snap / "sha256sums")


def _write_manifest(snap: Path, manifest: dict[str, Any]) -> None:
    tmp = snap / ".manifest.json.tmp"
    tmp.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, snap / "manifest.json")


def take(
    env: OpsEnv,
    name: str,
    reference: datetime | None = None,
    findquery: bytes | None = None,
    now: datetime | None = None,
) -> Report:
    """`demo-snapshot`: recovery, the §6.2 checks, then the copy; the manifest is written last."""
    rep = Report()
    target = env.snapshot(name)
    engine = _engine(env)
    try:
        if done := recover(env, engine):
            rep.say(f"recovered {len(done)} pending journal entries")
        if problems := snapshot_problems(env, engine, name):
            rep.problems = problems
            return rep
        env.snapshots.mkdir(parents=True, exist_ok=True)
        _own(env, env.snapshots)
        work = env.snapshots / f".{name}.partial"
        if work.exists():
            shutil.rmtree(work)
        work.mkdir()
        pg_run("pg_dump", env.conninfo, "-Fc", *EXCLUDE_DATA, "-f", str(work / "db.dump"))
        for tree in TREES:
            src = env.data / tree
            if src.is_dir():
                mirror(src, work / "data" / tree)
            else:
                (work / "data" / tree).mkdir(parents=True)
        if env.hermes is not None:
            hermes.snapshot_part(env.hermes, work / "hermes")
            if problems := checks.hermes_problems(work / "hermes"):
                rep.problems = problems
                shutil.rmtree(work)
                return rep
        if findquery is not None:
            (work / FINDQUERY).write_text(_fixture(engine, findquery), encoding="utf-8")
        write_sums(work)
        created = now or datetime.now(UTC)
        _write_manifest(
            work,
            {
                "v": 1,
                "name": name,
                "created_at": created.isoformat(),
                "reference_instant": (reference or created).isoformat(),
                "alembic_revision": head_revision(),
                "prompt_versions": _prompt_versions(),
                "mona_version": __version__,
                "counts": _counts(engine),
            },
        )
        old = env.snapshots / f".{name}.old"
        if target.exists():
            os.replace(target, old)
        os.replace(work, target)
        if old.exists():
            shutil.rmtree(old)
        chown_tree(target, env.data_owner)
        rep.say(f"snapshot {name} written")
        return rep
    finally:
        engine.dispose()


def _fixture(engine: Engine, cases_json: bytes) -> str:
    """The pdf.js-checked `mona pipeline evidence` cases, keyed by sha256 (ids change per run)."""
    cases = json.loads(cases_json)
    ids = sorted({c["document_id"] for c in cases})
    with engine.connect() as conn:
        q = text("SELECT id, sha256 FROM documents WHERE id = ANY(:ids)")
        shas = dict(conn.execute(q, {"ids": ids}).all())
    missing = [i for i in ids if i not in shas]
    if missing:
        raise OpsError(f"findQuery cases name {len(missing)} unknown documents")
    out = sorted(
        ({"sha256": shas[c["document_id"]], "field": c["field"], "page": c["page"],
          "find_query": c["find_query"]} for c in cases),
        key=lambda c: (c["sha256"], c["field"]),
    )  # fmt: skip
    return json.dumps(out, indent=1, ensure_ascii=False) + "\n"


def findquery_problems(engine: Engine, snap: Path) -> tuple[int, int, list[str]]:
    """Plan §6.3 fixture check: each rehearsed field still has its pdf.js-checked `findQuery`.
    Returns (checked, absent documents, problems)."""
    path = snap / FINDQUERY
    if not path.is_file():
        return 0, 0, []
    cases = json.loads(path.read_text(encoding="utf-8"))
    checked = absent = 0
    out = []
    q = text(
        "SELECT ef.page, ef.find_query, ef.verified FROM documents d"
        " JOIN extraction_fields ef ON ef.extraction_id = d.extraction_id"
        " WHERE d.sha256 = :sha AND ef.key = :field AND d.deleted_at IS NULL"
    )
    with engine.connect() as conn:
        present = set(conn.execute(text("SELECT sha256 FROM documents")).scalars())
        for c in cases:
            if c["sha256"] not in present:
                absent += 1
                continue
            checked += 1
            row = conn.execute(q, {"sha": c["sha256"], "field": c["field"]}).first()
            if (
                row is None
                or not row.verified
                or (row.page, row.find_query) != (c["page"], c["find_query"])
            ):
                out.append(f"findQuery changed: {c['sha256'][:12]} {c['field']}")
    return checked, absent, out


RESET_STATE = ".reset-state.json"


def postcheck(env: OpsEnv, name: str) -> Report:
    """§6.3 step 7 once the services are up: invariants, recovery, the brief job, findQuery."""
    rep = Report()
    engine = _engine(env)
    try:
        if done := recover(env, engine):
            rep.problems.append(f"recovery found {len(done)} pending entries")
        with engine.connect() as conn:
            rep.problems += checks.tree_problems(conn, Roots.at(env.data))
            if checks.recovery_left(conn):
                rep.problems.append("pending journal entries remain")
        state_file = env.snapshots / RESET_STATE
        if env.hermes is not None and state_file.is_file():
            expected = json.loads(state_file.read_text(encoding="utf-8")).get("jobs", [])
            if hermes.job_ids(env.hermes) != expected:
                rep.problems.append("the brief job list changed across the reset")
            rep.say(f"brief jobs installed: {len(expected)}")
        checked, absent, problems = findquery_problems(engine, env.snapshot(name))
        rep.problems += problems
        rep.say(f"findQuery fixture: {checked} fields checked, {absent} for absent documents")
        return rep
    finally:
        engine.dispose()


def read_manifest(snap: Path) -> dict[str, Any]:
    path = snap / "manifest.json"
    if not path.is_file():
        raise OpsError(f"no snapshot at {snap.name} (manifest.json missing)")
    return json.loads(path.read_text(encoding="utf-8"))


def verify(env: OpsEnv, name: str) -> dict[str, Any]:
    """§6.3 step 1: every file matches `sha256sums` and the schema is the current head."""
    snap = env.snapshot(name)
    manifest = read_manifest(snap)
    listed = {}
    for line in (snap / "sha256sums").read_text(encoding="utf-8").splitlines():
        digest, _, rel = line.partition("  ")
        listed[rel] = digest
    present = {r for r in files_under(snap) if r not in ("sha256sums", "manifest.json")}
    if set(listed) != present:
        raise OpsError("the snapshot's files do not match sha256sums (missing or extra files)")
    bad = [rel for rel, digest in listed.items() if sha256_path(snap / rel) != digest]
    if bad:
        raise OpsError(f"sha256 mismatch in {len(bad)} snapshot files")
    if manifest.get("alembic_revision") != head_revision():
        raise OpsError("the snapshot is from another schema version; rebuild it")
    return manifest


def refresh_textcache(env: OpsEnv, name: str, now: datetime | None = None) -> None:
    """`demo-snapshot --refresh-textcache`: only data/textcache/, the sums and `created_at`."""
    snap = env.snapshot(name)
    manifest = verify(env, name)
    src = env.data / "textcache"
    src.mkdir(parents=True, exist_ok=True)
    mirror(src, snap / "data" / "textcache")
    write_sums(snap)
    manifest["created_at"] = (now or datetime.now(UTC)).isoformat()
    _write_manifest(snap, manifest)
    chown_tree(snap, env.data_owner)


def restore_db(env: OpsEnv, dump: Path) -> None:
    with psycopg.connect(env.conninfo, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
    pg_run("pg_restore", env.conninfo, "--exit-on-error", "--no-owner", str(dump))
    migrate(env.url)


def restore(env: OpsEnv, name: str, anchor_day: date | None, now: datetime | None = None) -> Report:
    """§6.3 steps 1, 3–5 (the services are stopped by the host wrapper around it)."""
    rep = Report()
    snap = env.snapshot(name)
    manifest = verify(env, name)
    engine = _engine(env)
    try:
        if done := recover(env, engine):
            rep.say(f"recovered {len(done)} pending journal entries before the restore")
        engine.dispose()
        restore_db(env, snap / "db.dump")
        for tree in TREES:
            mirror(snap / "data" / tree, env.data / tree)
            chown_tree(env.data / tree, env.data_owner)
        empty_dir(env.data / "exports")
        chown_tree(env.data / "exports", env.data_owner)
        t0 = datetime.fromisoformat(manifest["reference_instant"])
        t1 = anchor.target_instant(anchor_day, now or datetime.now(UTC))
        delta = anchor.shift_seconds(t0, t1)
        with engine.begin() as conn:
            anchor.reanchor(conn, delta)
        rep.say(f"anchor {t1.isoformat()}, shift {delta} s")
        if env.hermes is not None:
            hermes.restore_part(snap / "hermes", env.hermes)
            with engine.connect() as conn:
                memory.write(conn, env.hermes)
            hermes.install_config(env.hermes, env.hermes_seed, env.env, env.hermes_env_keys)
            jobs = hermes.reset_cron(env.hermes)
            (env.snapshots / RESET_STATE).write_text(json.dumps({"jobs": jobs}), encoding="utf-8")
            _own(env, env.snapshots, env.snapshots / RESET_STATE)
            rep.say(f"brief jobs kept: {len(jobs)}")
            chown_tree(env.hermes, env.hermes_owner)
            from mona.demo.fingerprint import fingerprint

            h = fingerprint(env, hermes_only=True)["hermes"]
            rep.say(f"Hermes files restored: {h['files']}, sha256 {h['sha256'][:16]}")
            rep.problems += checks.hermes_problems(env.hermes)
        with engine.connect() as conn:
            rep.problems += checks.db_problems(conn)
            rep.problems += checks.tree_problems(conn, Roots.at(env.data))
            if name in checks.STAGE_NAMES:
                rep.problems += checks.stage_problems(conn)
        counts = _counts(engine)
        rep.say(", ".join(f"{k} {v}" for k, v in counts.items()))
        return rep
    finally:
        engine.dispose()

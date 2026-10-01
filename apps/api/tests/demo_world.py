"""A scratch stage for C9 §8 test 8: demo seed, a filed synthetic batch, a fake Hermes profile."""

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, text

from mona.demo.anchor import timestamp_columns
from mona.demo.tools import OpsEnv
from tests.pipeline_world import ANCHOR, RECORDED, Pipeline, content_for

BATCH = ["syn-urssaf-call", "syn-agipi-per", "syn-oxyleo-prep", "syn-unreadable"]
NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
DAY = date(2026, 9, 28)
CONFIG = "model:\n  default: test\n"
JOBS = {"jobs": [{"id": "job0brief", "name": "morning-brief", "schedule": {"expr": "30 7 * * *"}}]}


def make_hermes(home: Path) -> Path:
    """The pieces of a Hermes profile the snapshot and the reset care about."""
    for d in ("memories", "skills/note-taking", "cache/documents", "cache/images", "sessions",
              "logs", "cron/output"):  # fmt: skip
        (home / d).mkdir(parents=True, exist_ok=True)
    (home / "SOUL.md").write_text("# Mona\n", encoding="utf-8")
    (home / "skills/note-taking/SKILL.md").write_text("a skill\n", encoding="utf-8")
    (home / "config.yaml").write_text("live: true\n", encoding="utf-8")
    (home / "cron/jobs.json").write_text(json.dumps(JOBS), encoding="utf-8")
    con = sqlite3.connect(home / "state.db")
    with con:
        for t in ("sessions", "messages", "system_prompts"):
            con.execute(f"CREATE TABLE {t} (id INTEGER PRIMARY KEY, body TEXT)")
        con.execute("CREATE TABLE state_meta (k TEXT PRIMARY KEY, v TEXT)")
        con.execute("INSERT INTO state_meta VALUES ('schema', '1')")
    con.close()
    return home


def chat_in_hermes(home: Path) -> None:
    for d in ("sessions", "cron/output", "cache/documents"):
        (home / d).mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(home / "state.db")
    with con:
        con.execute("INSERT INTO sessions (body) VALUES ('conv')")
        con.execute("INSERT INTO messages (body) VALUES ('hello')")
    con.close()
    (home / "sessions" / "session_1.json").write_text("{}", encoding="utf-8")
    (home / "cron" / "output" / "brief.md").write_text("past brief", encoding="utf-8")
    (home / "cache" / "documents" / "upload.pdf").write_bytes(b"%PDF")


@dataclass
class Stage:
    env: OpsEnv
    p: Pipeline
    engine: Engine
    review: str
    filed: list[str]


def build(engine: Engine, url: str, root: Path) -> Stage:
    p = Pipeline(engine, root / "data")
    intake = p.drop_synthetic(BATCH)
    sha = p.cache_text(content_for("syn-sie-letter"), "syn-sie-letter")
    p.cache_model(sha, {**RECORDED["outputs"]["syn-sie-letter"], "entity": None})
    review = p.drop_synthetic(["syn-sie-letter"], outputs=False)
    p.drain()
    seed = root / "seed"
    seed.mkdir()
    (seed / "config.yaml").write_text(CONFIG, encoding="utf-8")
    env = OpsEnv(url=url, data=root / "data", hermes=make_hermes(root / "hermes"), hermes_seed=seed)
    filed = [i.document_id for i in intake.items if i.document_id]
    return Stage(env, p, engine, review.items[0].document_id, filed)  # type: ignore[arg-type]


SKIP_TABLES = ("alembic_version",)


def rows(engine: Engine) -> dict[str, list[dict[str, Any]]]:
    """Every row of every table but the queue's, as JSON, timestamps parsed."""
    out = {}
    with engine.connect() as conn:
        ts = timestamp_columns(conn)
        tables = conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
                " AND table_type = 'BASE TABLE' AND table_name NOT LIKE 'procrastinate%'"
            )
        ).scalars()
        for t in sorted(set(tables) - set(SKIP_TABLES)):
            got = []
            for (r,) in conn.execute(text(f'SELECT to_jsonb(x) FROM "{t}" x')):
                for c in ts.get(t, []):
                    if r.get(c) is not None:
                        r[c] = datetime.fromisoformat(r[c])
                got.append(r)
            out[t] = got
    return out


def shifted(before: dict[str, list[dict[str, Any]]], ts: dict[str, list[str]], delta: timedelta):
    """What `before` must become under re-anchoring by `delta`."""
    out = {}
    for t, rs in before.items():
        new = []
        for r in rs:
            r = json.loads(json.dumps(r, default=str))
            for c in ts.get(t, []):
                if r.get(c) is not None:
                    r[c] = datetime.fromisoformat(r[c]) + delta
            if t == "file_ops":
                for side in ("before", "after"):
                    s = r.get(side) or {}
                    if s.get("filed_at"):
                        moved = datetime.fromisoformat(s["filed_at"]) + delta
                        s["filed_at"] = moved.isoformat().replace("+00:00", "Z")
            if t == "profile":
                r["locked_at"] = None
            new.append(r)
        out[t] = new
    return out


def canonical(rs: dict[str, list[dict[str, Any]]]) -> dict[str, list[str]]:
    def norm(v: Any) -> Any:
        return v.astimezone(UTC).isoformat() if isinstance(v, datetime) else v

    return {
        t: sorted(json.dumps({k: norm(v) for k, v in r.items()}, sort_keys=True, default=str)
                  for r in v)
        for t, v in rs.items()
    }  # fmt: skip


def snapshot_reference() -> datetime:
    return ANCHOR

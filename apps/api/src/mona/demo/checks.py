"""C9 §6.2: what a snapshot must be. Each check returns problems; an empty list means it holds."""

import os
import sqlite3
from pathlib import Path

from sqlalchemy import Connection, select, text

from mona.fileops import Roots, sha256_file
from mona.fileops.state import T, undo_state

CHAT_TABLES = ("conversations", "chat_turns", "card_events", "card_action_notes")
HERMES_CONVERSATION_TABLES = ("sessions", "messages", "system_prompts")
STAGE_NAMES = ("demo", "demo-prefiled")


def _count(conn: Connection, sql: str) -> int:
    return int(conn.execute(text(sql)).scalar() or 0)


def _table_exists(conn: Connection, name: str) -> bool:
    found = conn.execute(text("SELECT to_regclass(:t)"), {"t": f"public.{name}"}).scalar()
    return found is not None


def db_problems(conn: Connection) -> list[str]:
    """§6.2 items 1–4 (journal, chat, running work, rule tier)."""
    out = []

    def need_zero(sql: str, what: str) -> None:
        if n := _count(conn, sql):
            out.append(f"{n} {what}")

    need_zero("SELECT count(*) FROM file_ops WHERE fs_state = 'pending'", "pending journal entries")
    for t in CHAT_TABLES:
        need_zero(f"SELECT count(*) FROM {t}", f"rows in {t}")
    need_zero("SELECT count(*) FROM batches WHERE status = 'running'", "running batches")
    need_zero("SELECT count(*) FROM batches WHERE visitor", "visitor batches")
    need_zero(
        "SELECT count(*) FROM interviews WHERE status = 'generating'", "generating interviews"
    )
    if _table_exists(conn, "procrastinate_jobs"):
        need_zero("SELECT count(*) FROM procrastinate_jobs WHERE status = 'doing'", "doing jobs")
        need_zero(
            "SELECT count(*) FROM procrastinate_jobs j WHERE status = 'todo' AND NOT EXISTS"
            " (SELECT 1 FROM procrastinate_periodic_defers p WHERE p.job_id = j.id)",
            "queued jobs",
        )
    need_zero("SELECT count(*) FROM rules WHERE source <> 'seed'", "rules not from the seed")
    need_zero("SELECT count(*) FROM interview_answers", "interview answers")
    return out


def _adoption_copies(conn: Connection) -> set[str]:
    f = T["file_ops"]
    out = set()
    adopted = text("fs_state = 'done' AND coalesce((after->>'adopted')::boolean, false)")
    for e in conn.execute(select(f).where(adopted)).mappings():
        if undo_state(conn, e) != "undone":
            out.add(e["after"]["trash_copy"])
    return out


def tree_problems(conn: Connection, roots: Roots) -> list[str]:
    """C7 invariants 1 (mirror) and 2 (no strays) over inbox, archive and trash."""
    out = []
    expected: dict[str, set[str]] = {"inbox": set(), "archive": set(), "trash": set()}
    for d in conn.execute(select(T["documents"])).mappings():
        p = roots.root(d["location"]) / d["current_path"]
        if p.is_symlink() or not p.is_file():
            out.append(f"document {d['id']}: no file in {d['location']}")
        elif sha256_file(p) != d["sha256"]:
            out.append(f"document {d['id']}: wrong bytes in {d['location']}")
        expected[d["location"]].add(d["current_path"])
    expected["trash"] |= _adoption_copies(conn)
    for loc, paths in expected.items():
        root = roots.root(loc)
        for dirpath, _, names in os.walk(root):
            for n in names:
                rel = (Path(dirpath) / n).relative_to(root).as_posix()
                if rel not in paths:
                    out.append(f"stray file in {loc}")
    return out


def hermes_problems(hermes: Path) -> list[str]:
    """§6.2 item 6 on a Hermes profile directory (live or snapshot part)."""
    out = []
    db = hermes / "state.db"
    if db.exists():
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            rows = con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            tables = {r[0] for r in rows}
            for t in HERMES_CONVERSATION_TABLES:
                if t in tables and (n := con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]):
                    out.append(f"{n} rows in Hermes {t}")
        finally:
            con.close()
    output = hermes / "cron" / "output"
    if output.is_dir() and any(p.is_file() for p in output.rglob("*")):
        out.append("Hermes cron/output holds past outputs")
    for sub in ("documents", "images"):
        d = hermes / "cache" / sub
        if d.exists() and any(d.iterdir()):
            out.append(f"Hermes cache/{sub} is not empty")
    return out


def stage_problems(conn: Connection) -> list[str]:
    """§6.2 item 8 / §6.7: the stage settings a `demo` or `demo-prefiled` snapshot holds."""
    out = []
    settings = conn.execute(select(T["settings"])).mappings().first()
    profile = conn.execute(select(T["profile"])).mappings().first()
    if settings is None or profile is None:
        return ["no settings or profile row"]
    cols = set(conn.execute(text("SELECT * FROM settings LIMIT 1")).keys())
    if "debrief_early_min" not in cols:
        out.append("settings.debrief_early_min is missing (amendment A9 migration)")
    else:
        early = conn.execute(text("SELECT debrief_early_min FROM settings")).scalar()
        if early not in (7, 8):
            out.append(f"settings.debrief_early_min is {early}, not 7 or 8")
    if settings["debrief_queue_threshold"] != 5:
        out.append("settings.debrief_queue_threshold is not 5")
    if profile["auto_lock_minutes"] != 120:
        out.append("profile.auto_lock_minutes is not 120")
    if profile["name"] == settings["practice_name"]:
        out.append("profile.name is the practice name, not the owner's form of address")
    return out


def recovery_left(conn: Connection) -> int:
    return _count(conn, "SELECT count(*) FROM file_ops WHERE fs_state = 'pending'")

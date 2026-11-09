"""C9 §8 test 8 (snapshot and reset) on a scratch stage: §6.1–§6.4 and the §6.2 refusals."""

import hashlib
import json
import sqlite3
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import create_engine, text

from mona.demo import anchor, checks
from mona.demo.anchor import timestamp_columns
from mona.demo.fingerprint import fingerprint
from mona.demo.hermes import job_ids
from mona.demo.snapshot import (
    EXCLUDE_DATA,
    postcheck,
    refresh_textcache,
    restore,
    take,
    verify,
    write_sums,
)
from mona.demo.tools import OpsEnv, OpsError, pg_run
from mona.migrate import chain_revisions
from mona.services.corrections import correct_document
from mona.services.undo import delete_document
from tests.demo_world import (
    CONFIG,
    DAY,
    JOBS,
    NOW,
    SOUL,
    build,
    canonical,
    chat_in_hermes,
    rows,
    shifted,
    snapshot_reference,
)
from tests.pg import alembic, scratch_db, sqlalchemy_url_for
from tests.pipeline_world import DEMO_SEED, Pipeline

ULID = "01m3tgvaan1cwn6fb6q9y56wcw"
CONVERSATION = f"INSERT INTO conversations (id, title) VALUES ('cnv_{ULID}', 't')"
PENDING = (
    "UPDATE file_ops SET fs_state = 'pending', at = now() WHERE id = (SELECT max(id) FROM file_ops)"
)
ANSWERED = f"""
INSERT INTO interviews (id, kind, status, scope, lang)
VALUES ('int_{ULID}', 'debrief', 'done', '{{}}', 'en');
INSERT INTO interview_questions (id, interview_id, ordinal, text, impact, affected_document_ids,
  evidence, options, suggestion_confidence)
VALUES ('qst_{ULID}', 'int_{ULID}', 1, 'q', 1, '{{}}', '[]', '[]', 50);
INSERT INTO interview_answers (id, question_id, option_id, actor, via)
VALUES ('ans_{ULID}', 'qst_{ULID}', 'a', 'user', 'ui');
UPDATE rules SET source = 'interview' WHERE key = (SELECT min(key) FROM rules);
"""
AUTH_SESSIONS = """
INSERT INTO auth_sessions (id, token_hash, expires_at)
VALUES ('ses_01m3aaaaaaaaaaaaaaaaaaaaaa', repeat('a', 64), now() + interval '1 day');
"""
FTS = "SELECT count(*) FROM documents WHERE fts @@ plainto_tsquery('mona', 'appel')"
VERIFIED = """
SELECT d.id, ef.key, ef.page, ef.find_query FROM documents d
JOIN extraction_fields ef ON ef.extraction_id = d.extraction_id
WHERE ef.verified AND ef.find_query IS NOT NULL
"""


@pytest.fixture
def stage(l1m2_demo_template, tmp_path):
    with scratch_db(template=l1m2_demo_template) as db:
        url = sqlalchemy_url_for(db)
        engine = create_engine(url)
        try:
            yield build(engine, url, tmp_path)
        finally:
            engine.dispose()


def sql(stage, statement: str) -> None:
    with stage.engine.begin() as conn:
        conn.exec_driver_sql(statement)


def count(stage, statement: str) -> int:
    with stage.engine.connect() as conn:
        return conn.execute(text(statement)).scalar_one()


def snap(stage, name="scratch", findquery=None):
    rep = take(stage.env, name, snapshot_reference(), findquery, NOW)
    assert rep.problems == []
    return rep


def rehearse(stage) -> None:
    """What a rehearsal changes: a review resolved, a document deleted, chat, exports, Hermes."""
    ctx = stage.p.ctx
    correct_document(ctx, stage.review, actor="user", via="ui", entity="mdd", category="tax")
    delete_document(ctx, stage.filed[1], actor="user", via="ui")
    sql(stage, CONVERSATION)
    exports = stage.env.data / "exports"
    exports.mkdir(exist_ok=True)
    (exports / "pack.zip").write_bytes(b"zip")
    chat_in_hermes(stage.env.hermes)


def reset(stage, day=DAY):
    rep = restore(stage.env, "scratch", day, now=NOW)
    assert rep.problems == []
    return rep


def test_two_resets_leave_the_same_database_trees_and_hermes_files(stage):
    snap(stage)
    rehearse(stage)
    reset(stage)
    first = fingerprint(stage.env)
    rehearse(stage)
    reset(stage)
    assert fingerprint(stage.env) == first


def test_a_review_document_resolved_in_rehearsal_is_back_in_the_inbox(stage):
    snap(stage)
    path = stage.env.data / "inbox" / stage.p.row(stage.review)["current_path"]
    rehearse(stage)
    assert stage.p.row(stage.review)["location"] == "archive" and not path.exists()
    reset(stage)
    row = stage.p.row(stage.review)
    assert (row["location"], row["status"]) == ("inbox", "review")
    assert path.is_file()
    deleted = stage.p.row(stage.filed[1])
    assert deleted["location"] == "archive" and deleted["deleted_at"] is None
    with stage.engine.connect() as conn:
        assert checks.tree_problems(conn, stage.p.ctx.ops.roots) == []
    assert not (stage.env.data / "exports" / "pack.zip").exists()


def test_every_timestamp_moves_by_delta_and_no_date_does(stage):
    snap(stage)
    before = rows(stage.engine)
    with stage.engine.connect() as conn:
        ts = timestamp_columns(conn)
    assert count(stage, "SELECT count(*) FROM file_ops WHERE after->>'filed_at' IS NOT NULL") > 0
    assert count(stage, "SELECT count(*) FROM documents WHERE doc_date IS NOT NULL") > 0
    rehearse(stage)
    rep = reset(stage)
    t1 = anchor.target_instant(DAY, NOW)
    delta = timedelta(seconds=anchor.shift_seconds(snapshot_reference(), t1))
    assert f"shift {int(delta.total_seconds())} s" in " ".join(rep.lines)
    assert canonical(rows(stage.engine)) == canonical(shifted(before, ts, delta))


def test_after_reset_extensions_search_and_the_job_queue_work(stage):
    snap(stage)
    rehearse(stage)
    reset(stage)
    assert (
        count(stage, "SELECT count(*) FROM pg_extension WHERE extname IN ('unaccent', 'pg_trgm')")
        == 2
    )
    assert count(stage, "SELECT count(*) FROM pg_ts_config WHERE cfgname = 'mona'") == 1
    assert count(stage, "SELECT count(*) FROM procrastinate_jobs") == 0
    assert count(stage, FTS) >= 1
    p = Pipeline(stage.engine, stage.env.data)
    doc = p.drop_synthetic(["syn-sie-letter"]).items[0].document_id
    p.drain()
    assert p.row(doc)["pipeline_stage"] == "done"


def test_no_conversation_survives_and_the_brief_job_is_kept(stage):
    snap(stage)
    rehearse(stage)
    reset(stage)
    home = stage.env.hermes
    for t in checks.CHAT_TABLES:
        assert count(stage, f"SELECT count(*) FROM {t}") == 0, t
    con = sqlite3.connect(home / "state.db")
    for t in checks.HERMES_CONVERSATION_TABLES:
        assert con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] == 0, t
    con.close()
    assert not (home / "sessions").exists() and not (home / "logs").exists()
    assert list((home / "cache" / "documents").iterdir()) == []
    assert sorted(p.name for p in (home / "cron").iterdir()) == ["jobs.json"]
    assert job_ids(home) == [JOBS["jobs"][0]["id"]]
    assert (home / "config.yaml").read_text() == CONFIG
    assert (home / "SOUL.md").read_text() == SOUL
    assert (home / ".env").read_text() == ""
    assert "Claudiu" in (home / "memories" / "USER.md").read_text()
    out = postcheck(stage.env, "scratch")
    assert out.problems == [] and "brief jobs installed: 1" in out.lines


def test_a_reset_installs_the_repos_soul_over_an_old_snapshots(stage):
    snap(stage)
    part = stage.env.snapshot("scratch") / "hermes"
    assert not (part / "SOUL.md").exists()
    (part / "SOUL.md").write_text("# Mona, an old stage SOUL\n", encoding="utf-8")
    write_sums(stage.env.snapshot("scratch"))
    rehearse(stage)
    reset(stage)
    assert (stage.env.hermes / "SOUL.md").read_text() == SOUL
    first = fingerprint(stage.env)
    rehearse(stage)
    reset(stage)
    assert fingerprint(stage.env) == first


def test_the_findquery_fixture_check_names_a_changed_field(stage):
    with stage.engine.connect() as conn:
        cases = [
            {"document_id": r.id, "field": r.key, "page": r.page, "find_query": r.find_query}
            for r in conn.execute(text(VERIFIED))
        ]
    assert cases
    snap(stage, findquery=json.dumps(cases).encode())
    reset(stage)
    assert postcheck(stage.env, "scratch").problems == []
    sql(stage, "UPDATE extraction_fields SET find_query = 'elsewhere' WHERE key = 'amount'")
    assert any(p.startswith("findQuery changed") for p in postcheck(stage.env, "scratch").problems)


# --- refused at build (§6.2) ---


def refused(stage, name="scratch"):
    rep = take(stage.env, name, snapshot_reference(), now=NOW)
    assert not (stage.env.snapshots / name).exists()
    return rep.problems


def test_refuses_a_visitor_batch(stage):
    stage.p.drop_synthetic(["syn-visitor-photo"], visitor=True)
    stage.p.drain()
    assert "1 visitor batches" in refused(stage)


def test_a_pending_entry_is_refused_and_recovery_runs_first(stage):
    sql(stage, PENDING)
    with stage.engine.connect() as conn:
        assert "1 pending journal entries" in checks.db_problems(conn)
    rep = take(stage.env, "scratch", snapshot_reference(), now=NOW)
    assert rep.problems == [] and "recovered 1 pending journal entries" in rep.lines
    with stage.engine.connect() as conn:
        assert checks.recovery_left(conn) == 0


def test_refuses_rules_learned_live(stage):
    from mona.seed.loader import import_rules

    with stage.engine.begin() as conn:
        import_rules(conn, DEMO_SEED / "rules.learned.yaml")
    assert "3 rules not from the seed" in refused(stage)


def test_the_disabled_seed_fallback_copies_are_accepted(stage):
    disabled = "SELECT count(*) FROM rules WHERE state = 'disabled' AND source = 'seed'"
    assert count(stage, disabled) == 3
    snap(stage)


def test_refuses_an_answered_debrief_question(stage):
    sql(stage, ANSWERED)
    problems = refused(stage)
    assert "1 interview answers" in problems and "1 rules not from the seed" in problems


def test_refuses_chat_rows_and_a_hermes_conversation(stage):
    chat_in_hermes(stage.env.hermes)
    sql(stage, CONVERSATION)
    problems = refused(stage)
    assert "1 rows in conversations" in problems
    assert {"1 rows in Hermes sessions", "1 rows in Hermes messages"} <= set(problems)
    assert "Hermes cron/output holds past outputs" in problems
    assert "Hermes cache/documents is not empty" in problems


def test_refuses_a_stray_file_and_a_missing_file(stage):
    (stage.env.data / "inbox" / "stray.pdf").write_bytes(b"x")
    (stage.env.data / "archive" / stage.p.row(stage.filed[0])["current_path"]).unlink()
    problems = refused(stage)
    assert "stray file in inbox" in problems
    assert f"document {stage.filed[0]}: no file in archive" in problems


def test_a_stage_snapshot_needs_the_stage_settings(stage):
    assert "profile.auto_lock_minutes is not 120" in refused(stage, "demo")


# --- refused at reset (§6.3 step 1) ---


def test_reset_refuses_a_tampered_snapshot_or_another_schema(stage):
    snap(stage)
    dump = stage.env.snapshot("scratch") / "db.dump"
    dump.write_bytes(dump.read_bytes() + b"x")
    with pytest.raises(OpsError, match="sha256 mismatch"):
        verify(stage.env, "scratch")
    snap(stage)
    m = stage.env.snapshot("scratch") / "manifest.json"
    m.write_text(m.read_text().replace('"alembic_revision": "', '"alembic_revision": "x'))
    with pytest.raises(OpsError, match="newer or unknown schema version"):
        restore(stage.env, "scratch", DAY, now=NOW)


# --- an older snapshot (A38) ---

OLD_ROWS = """
INSERT INTO batches (id, source, status) VALUES ('bat_{u}', 'drop', 'done');
INSERT INTO op_groups (id, kind, actor, via, batch_id)
VALUES ('grp_{u}', 'intake_batch', 'mona', 'pipeline', 'bat_{u}');
INSERT INTO documents (id, sha256, original_name, mime_type, size_bytes, source, batch_id,
  arrived_at, location, current_path, status, pipeline_stage)
VALUES ('doc_{u}', '{sha}', 'letter.pdf', 'application/pdf', {size}, 'drop', 'bat_{u}',
  '2026-09-28 05:00:00+00', 'inbox', 'doc_{u}.pdf', 'review', 'done');
"""


def old_snapshot(env: OpsEnv, url: str, revision: str, pdf: bytes) -> None:
    """A snapshot as a release at `revision` wrote it: dump, trees, sums, manifest."""
    engine = create_engine(url)
    try:
        sha = hashlib.sha256(pdf).hexdigest()
        with engine.begin() as conn:
            conn.exec_driver_sql(OLD_ROWS.format(u=ULID, sha=sha, size=len(pdf)))
    finally:
        engine.dispose()
    snap = env.snapshot("older")
    for tree in ("inbox", "archive", "trash", "textcache", "config"):
        (snap / "data" / tree).mkdir(parents=True)
    (snap / "data" / "inbox" / f"doc_{ULID}.pdf").write_bytes(pdf)
    pg_run("pg_dump", env.conninfo, "-Fc", *EXCLUDE_DATA, "-f", str(snap / "db.dump"))
    write_sums(snap)
    manifest = {"v": 1, "name": "older", "created_at": NOW.isoformat(),
                "reference_instant": snapshot_reference().isoformat(),
                "alembic_revision": revision, "prompt_versions": {"c5": None, "c6": None},
                "mona_version": "0", "counts": {"documents": 1}}  # fmt: skip
    (snap / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_a_snapshot_one_revision_old_restores_and_migrates_to_head(tmp_path):
    head, previous = chain_revisions()[:2]
    pdf = b"%PDF-1.4\n% a fictional letter\n%%EOF\n"
    with scratch_db() as db:
        url = sqlalchemy_url_for(db)
        env = OpsEnv(url=url, data=tmp_path / "data")
        alembic(db, "upgrade", previous)
        old_snapshot(env, url, previous, pdf)
        alembic(db, "upgrade", "head")
        engine = create_engine(url)
        try:
            with engine.begin() as conn:
                conn.exec_driver_sql("DELETE FROM documents; DELETE FROM op_groups;")
            assert verify(env, "older")["alembic_revision"] == previous
            refresh_textcache(env, "older", now=NOW)
            rep = restore(env, "older", None, now=NOW)
            assert rep.problems == []
            assert f"schema {previous} → {head}" in rep.lines
            with engine.connect() as conn:
                assert conn.execute(text("SELECT version_num FROM alembic_version")).all() == [
                    (head,)
                ]
                doc = conn.execute(
                    text("SELECT sha256, location, current_path, batch_id FROM documents")
                ).all()
            assert doc == [(hashlib.sha256(pdf).hexdigest(), "inbox", f"doc_{ULID}.pdf",
                            f"bat_{ULID}")]  # fmt: skip
            assert (env.data / "inbox" / f"doc_{ULID}.pdf").read_bytes() == pdf
            assert postcheck(env, "older").problems == []
        finally:
            engine.dispose()


@pytest.mark.parametrize("revision", ["9999", "0000", None])
def test_a_snapshot_from_a_newer_or_unknown_schema_is_refused(tmp_path, revision):
    env = OpsEnv(url="postgresql+psycopg://unused/none", data=tmp_path / "data")
    snap = env.snapshot("future")
    (snap / "data").mkdir(parents=True)
    write_sums(snap)
    (snap / "manifest.json").write_text(json.dumps({"alembic_revision": revision}))
    with pytest.raises(OpsError, match="newer or unknown schema version; update Mona or rebuild"):
        verify(env, "future")
    with pytest.raises(OpsError, match="newer or unknown"):
        refresh_textcache(env, "future", now=NOW)


# --- re-anchoring (§6.4) ---


def test_anchor_is_seven_paris_time_never_in_the_future():
    assert anchor.target_instant(date(2026, 9, 28), NOW) == datetime(2026, 9, 28, 5, 0, tzinfo=UTC)
    early = datetime(2026, 10, 1, 4, 0, tzinfo=UTC)
    assert anchor.target_instant(None, early) == early - timedelta(minutes=5)
    with pytest.raises(OpsError, match="after today"):
        anchor.target_instant(date(2026, 10, 2), NOW)
    t0 = datetime(2026, 10, 20, 5, 0, 0, 900000, tzinfo=UTC)
    assert anchor.shift_seconds(t0, datetime(2026, 10, 18, 5, 0, tzinfo=UTC)) == -2 * 86400


def test_refreshed_text_cache_carries_a_debrief_file_through_a_reset(stage):
    snap(stage)
    debrief = stage.env.data / "textcache" / "debrief" / f"{'a' * 32}.c6-v1.en.json"
    debrief.parent.mkdir(parents=True)
    debrief.write_text('{"v": 1}', encoding="utf-8")
    dump = (stage.env.snapshot("scratch") / "db.dump").read_bytes()
    refresh_textcache(stage.env, "scratch", now=NOW)
    assert (stage.env.snapshot("scratch") / "db.dump").read_bytes() == dump
    verify(stage.env, "scratch")
    debrief.unlink()
    reset(stage)
    assert debrief.read_text(encoding="utf-8") == '{"v": 1}'


def test_session_rows_are_tolerated_and_never_dumped(stage):
    sql(stage, AUTH_SESSIONS)
    snap(stage)
    reset(stage)
    assert count(stage, "SELECT count(*) FROM auth_sessions") == 0

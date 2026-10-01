import psycopg

from mona.migrate import apply_jobs_schema, migrate
from mona.settings import get_settings


def test_baseline_creates_search_extensions_and_jobs_schema():
    with psycopg.connect(get_settings().libpq_url) as conn:
        exts = {r[0] for r in conn.execute("SELECT extname FROM pg_extension")}
        jobs = conn.execute("SELECT to_regclass('procrastinate_jobs')").fetchone()
    assert {"unaccent", "pg_trgm"} <= exts
    assert jobs is not None and jobs[0] is not None


def test_migrate_is_idempotent():
    migrate()
    assert apply_jobs_schema() is False


def test_0006_sets_the_a18_defaults_and_leaves_existing_rows():
    from tests.pg import alembic, conninfo_for, scratch_db

    insert = "INSERT INTO settings (practice_name, iban_salt) VALUES ('p', '\\x00')"
    with scratch_db() as db:
        alembic(db, "upgrade", "0005")
        with psycopg.connect(conninfo_for(db)) as conn:
            conn.execute(insert)
        alembic(db, "upgrade", "0006")
        with psycopg.connect(conninfo_for(db)) as conn:
            kept = conn.execute("SELECT confidence_high, confidence_low FROM settings").fetchone()
            conn.execute("DELETE FROM settings")
            conn.execute(insert)
            fresh = conn.execute("SELECT confidence_high, confidence_low FROM settings").fetchone()
    assert (kept, fresh) == ((85, 60), (90, 75))

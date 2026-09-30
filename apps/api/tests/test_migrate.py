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

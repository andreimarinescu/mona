from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config
from procrastinate.schema import SchemaManager

from mona.settings import get_settings

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def alembic_config() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", get_settings().database_url.replace("%", "%%"))
    return cfg


def apply_jobs_schema() -> bool:
    """Apply the Procrastinate schema unless it is already there. Returns True if applied."""
    with psycopg.connect(get_settings().libpq_url) as conn:
        exists = conn.execute("SELECT to_regclass('procrastinate_jobs')").fetchone()
        if exists and exists[0] is not None:
            return False
        conn.execute(SchemaManager.get_schema())
    return True


def migrate() -> None:
    command.upgrade(alembic_config(), "head")
    apply_jobs_schema()

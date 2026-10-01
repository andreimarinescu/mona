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


def apply_jobs_schema(conninfo: str | None = None) -> bool:
    """Apply the Procrastinate schema unless it is already there. Returns True if applied."""
    with psycopg.connect(conninfo or get_settings().libpq_url) as conn:
        exists = conn.execute("SELECT to_regclass('procrastinate_jobs')").fetchone()
        if exists and exists[0] is not None:
            return False
        conn.execute(SchemaManager.get_schema())
    return True


def migrate(url: str | None = None) -> None:
    cfg = alembic_config()
    if url:
        cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    command.upgrade(cfg, "head")
    apply_jobs_schema(libpq(url) if url else None)


def libpq(url: str) -> str:
    """A SQLAlchemy URL without its driver suffix."""
    scheme, sep, rest = url.partition("://")
    return scheme.split("+", 1)[0] + sep + rest


def head_revision() -> str:
    from alembic.script import ScriptDirectory

    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    assert head is not None
    return head

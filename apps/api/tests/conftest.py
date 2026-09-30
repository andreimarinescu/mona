from pathlib import Path

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from sqlalchemy import create_engine

from mona.db import get_engine, get_sessionmaker, get_sync_engine, get_sync_sessionmaker
from mona.migrate import migrate
from mona.seed.loader import load_seed
from mona.settings import Settings, get_settings
from tests.pg import alembic, scratch_db, sqlalchemy_url_for
from tests.rows import CLEANUP

SEED = Path(__file__).parent / "fixtures" / "seed"
SERVICE_KEY = "k" * 32


@pytest.fixture(scope="session", autouse=True)
def database() -> None:
    params = conninfo_to_dict(get_settings().libpq_url)
    dbname = params["dbname"]
    with psycopg.connect(**{**params, "dbname": "postgres"}, autocommit=True) as conn:
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,)).fetchone():
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(dbname)))
    migrate()


@pytest.fixture(scope="session")
def seeded_template(database):
    """A migrated database holding the synthetic seed (all rule tiers)."""
    with scratch_db() as db:
        alembic(db, "upgrade", "head")
        engine = create_engine(sqlalchemy_url_for(db))
        try:
            with engine.begin() as conn:
                load_seed(
                    conn,
                    SEED,
                    settings=Settings(database_url=sqlalchemy_url_for(db), mona_owner_password="x"),
                    tier="all",
                    overlay=SEED / "overlay.yaml",
                )
        finally:
            engine.dispose()
        yield db


def _clear_caches() -> None:
    for f in (get_settings, get_engine, get_sessionmaker, get_sync_engine, get_sync_sessionmaker):
        f.cache_clear()


@pytest.fixture(scope="module")
async def app_db(seeded_template):
    """Points get_settings()/get_engine() at a fresh copy of the seeded database."""
    with scratch_db(template=seeded_template) as db, pytest.MonkeyPatch.context() as mp:
        mp.setenv("DATABASE_URL", sqlalchemy_url_for(db))
        mp.setenv("MONA_SERVICE_KEY", SERVICE_KEY)
        _clear_caches()
        try:
            yield db
        finally:
            await get_engine().dispose()
            _clear_caches()


@pytest.fixture
def clean(app_db) -> str:
    with psycopg.connect(get_settings().libpq_url) as conn:
        for stmt in CLEANUP:
            conn.execute(stmt)
    return app_db


@pytest.fixture(scope="module")
def migrated_engine():
    """A scratch database at head, private to the test module."""
    from sqlalchemy import create_engine

    from tests.pg import alembic, scratch_db, sqlalchemy_url_for

    with scratch_db() as db:
        alembic(db, "upgrade", "head")
        engine = create_engine(sqlalchemy_url_for(db), pool_size=8)
        try:
            yield engine
        finally:
            engine.dispose()


@pytest.fixture(scope="module")
def services_seed_template():
    """A database at head with the synthetic C5 §8.5 seed (both rule tiers) loaded."""
    from sqlalchemy import create_engine

    from tests.pg import alembic, scratch_db, sqlalchemy_url_for
    from tests.services_world import load_fixture_seed

    with scratch_db() as db:
        alembic(db, "upgrade", "head")
        engine = create_engine(sqlalchemy_url_for(db))
        load_fixture_seed(engine, sqlalchemy_url_for(db))
        engine.dispose()
        yield db


@pytest.fixture
def seeded_engine(services_seed_template):
    from sqlalchemy import create_engine

    from tests.pg import scratch_db, sqlalchemy_url_for

    with scratch_db(template=services_seed_template) as db:
        engine = create_engine(sqlalchemy_url_for(db), pool_size=8)
        try:
            yield engine
        finally:
            engine.dispose()

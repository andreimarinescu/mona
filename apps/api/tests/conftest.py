import os
import tempfile

os.environ["MONA_ENV"] = "dev"

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
os.environ.setdefault("MONA_DATA_DIR", tempfile.mkdtemp(prefix="mona-test-data-"))


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
    from procrastinate.schema import SchemaManager

    from tests.pg import conninfo_for

    with scratch_db() as db:
        alembic(db, "upgrade", "head")
        with psycopg.connect(conninfo_for(db)) as conn:
            conn.execute(SchemaManager.get_schema())
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


def _demo_template(tier: str):
    from sqlalchemy import create_engine

    from tests.pg import alembic, conninfo_for, scratch_db, sqlalchemy_url_for
    from tests.pipeline_world import apply_jobs_schema, load_demo_seed

    with scratch_db() as db:
        alembic(db, "upgrade", "head")
        apply_jobs_schema(conninfo_for(db))
        engine = create_engine(sqlalchemy_url_for(db))
        load_demo_seed(engine, sqlalchemy_url_for(db), tier)
        engine.dispose()
        yield db


@pytest.fixture(scope="session")
def l1m2_demo_template():
    """A database at head with the Procrastinate schema and demo/seed (pre-seeded tier)."""
    yield from _demo_template("preseeded")


@pytest.fixture(scope="session")
def l1m2_learned_template():
    """The same, with the rules the demo learns live (rules.learned.yaml) loaded too."""
    yield from _demo_template("all")


def _engine_on(template: str):
    from sqlalchemy import create_engine

    from tests.pg import scratch_db, sqlalchemy_url_for

    with scratch_db(template=template) as db:
        engine = create_engine(sqlalchemy_url_for(db), pool_size=8)
        try:
            yield engine
        finally:
            engine.dispose()


@pytest.fixture
def l1m2_demo_engine(l1m2_demo_template):
    yield from _engine_on(l1m2_demo_template)


@pytest.fixture
def l1m2_learned_engine(l1m2_learned_template):
    yield from _engine_on(l1m2_learned_template)


@pytest.fixture(scope="session")
def l4_template(database):
    """At head with the synthetic seed's pre-seeded rules and the Procrastinate schema."""
    from procrastinate.schema import SchemaManager

    from tests.pg import conninfo_for
    from tests.services_world import load_fixture_seed

    with scratch_db() as db:
        alembic(db, "upgrade", "head")
        engine = create_engine(sqlalchemy_url_for(db))
        load_fixture_seed(engine, sqlalchemy_url_for(db), tier="preseeded")
        engine.dispose()
        with psycopg.connect(conninfo_for(db)) as conn:
            conn.execute(SchemaManager.get_schema())
        yield db


@pytest.fixture
async def l4_db(l4_template, tmp_path):
    """A fresh copy of `l4_template` behind get_settings()/get_engine() and a tmp data dir."""
    from mona.workflow.common import get_ctx

    with scratch_db(template=l4_template) as db, pytest.MonkeyPatch.context() as mp:
        mp.setenv("DATABASE_URL", sqlalchemy_url_for(db))
        mp.setenv("MONA_SERVICE_KEY", SERVICE_KEY)
        mp.setenv("MONA_DATA_DIR", str(tmp_path / "data"))
        _clear_caches()
        get_ctx.cache_clear()
        try:
            yield db
        finally:
            await get_engine().dispose()
            get_sync_engine().dispose()
            _clear_caches()
            get_ctx.cache_clear()


@pytest.fixture
def l2_world(clean, tmp_path, monkeypatch):
    """The app's services context on a fresh data dir, plus a Services world to make documents."""
    from mona.api.deps import get_ctx
    from mona.api.session import throttle
    from tests.services_world import Services

    monkeypatch.setenv("MONA_DATA_DIR", str(tmp_path / "data"))
    get_settings.cache_clear()
    get_ctx.cache_clear()
    throttle.reset()
    with psycopg.connect(get_settings().libpq_url) as conn:
        conn.execute("DELETE FROM auth_sessions")
        conn.execute("DELETE FROM card_action_notes")
        conn.execute("UPDATE profile SET locked_at = NULL, locale = 'en'")
        conn.execute(
            "DELETE FROM rules WHERE key NOT IN ('opco-cabinet', 'talenz-studio',"
            " 'oxyleo-personal-tax', 'unim-business', 'agipi-per-by-person', 'hello-bank-lmnp')"
        )
        conn.execute(
            "UPDATE rules SET state = CASE key WHEN 'unim-business' THEN 'disabled'"
            " ELSE 'active' END"
        )
    world = Services(get_sync_engine(), tmp_path / "data")
    try:
        yield world
    finally:
        get_ctx.cache_clear()
        get_settings.cache_clear()

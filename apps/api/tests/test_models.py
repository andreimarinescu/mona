import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

from mona.db.models import Base
from tests.pg import alembic, scratch_db, sqlalchemy_url_for

IGNORED_PREFIXES = ("procrastinate_", "spike_")


def _include(name, type_, *_):
    return not (type_ == "table" and name and name.startswith(IGNORED_PREFIXES))


@pytest.fixture(scope="module")
def migrated_db():
    with scratch_db() as db:
        alembic(db, "upgrade", "head")
        yield db


def test_models_match_migrated_schema(migrated_db):
    engine = create_engine(sqlalchemy_url_for(migrated_db))
    try:
        with engine.connect() as conn:
            ctx = MigrationContext.configure(
                conn,
                opts={
                    "compare_type": True,
                    "compare_server_default": True,
                    "include_name": _include,
                },
            )
            diff = compare_metadata(ctx, Base.metadata)
    finally:
        engine.dispose()
    assert diff == []


def test_models_cover_every_table(migrated_db):
    engine = create_engine(sqlalchemy_url_for(migrated_db))
    try:
        with engine.connect() as conn:
            tables = {
                r[0]
                for r in conn.exec_driver_sql(
                    "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
                )
            }
    finally:
        engine.dispose()
    tables -= {"alembic_version"}
    tables = {t for t in tables if not t.startswith(IGNORED_PREFIXES)}
    assert tables == set(Base.metadata.tables)
    assert len(tables) == 34


async def test_async_session_uses_server_defaults(migrated_db):
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from mona.db.models import Entity, SubUnit

    engine = create_async_engine(sqlalchemy_url_for(migrated_db))
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            ent = Entity(key="cabinet", display_name="Cabinet Marchand", folder_name="Cabinet")
            session.add(ent)
            await session.flush()
            session.add(SubUnit(entity_id=ent.id, key="paul", label="Paul"))
            await session.commit()
        async with async_sessionmaker(engine)() as session:
            loaded = (await session.execute(select(Entity))).scalar_one()
            assert loaded.id.startswith("ent_") and loaded.visibility == "practice"
            assert loaded.aliases == [] and loaded.fy_end_month == 12
            assert [s.key for s in loaded.sub_units] == ["paul"]
    finally:
        await engine.dispose()

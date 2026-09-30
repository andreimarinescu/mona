import difflib

import psycopg

from tests.c1_sql import contract_ddl
from tests.pg import alembic, conninfo_for, schema_dump, scratch_db


def _diff(a: list[str], b: list[str]) -> str:
    return "\n".join(difflib.unified_diff(a, b, "contract", "migration", lineterm="", n=2))


def test_migration_head_equals_c1_contract_sql():
    with scratch_db() as contract_db, scratch_db() as migrated_db:
        with psycopg.connect(conninfo_for(contract_db)) as conn:
            conn.execute("CREATE EXTENSION unaccent")
            conn.execute("CREATE EXTENSION pg_trgm")
            for stmt in contract_ddl():
                conn.execute(stmt)
        alembic(migrated_db, "upgrade", "head")
        expected, actual = schema_dump(contract_db), schema_dump(migrated_db)
    assert any("CREATE TABLE public.documents" in line for line in expected)
    assert expected == actual, _diff(expected, actual)


def test_migration_round_trip():
    with scratch_db() as db:
        alembic(db, "upgrade", "head")
        first = schema_dump(db)
        alembic(db, "downgrade", "base")
        assert not [line for line in schema_dump(db) if line.startswith(("CREATE", "ALTER"))]
        alembic(db, "upgrade", "head")
        assert schema_dump(db) == first

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

from mona.migrate import migrate
from mona.settings import get_settings


@pytest.fixture(scope="session", autouse=True)
def database() -> None:
    params = conninfo_to_dict(get_settings().libpq_url)
    dbname = params["dbname"]
    with psycopg.connect(**{**params, "dbname": "postgres"}, autocommit=True) as conn:
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,)).fetchone():
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(dbname)))
    migrate()

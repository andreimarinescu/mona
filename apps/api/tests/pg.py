import os
import re
import shutil
import subprocess
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from alembic import command
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from mona.migrate import alembic_config
from mona.settings import get_settings

EXCLUDED_TABLES = ["alembic_version", "procrastinate_*", "spike_*"]


def admin_conninfo() -> str:
    return make_conninfo(get_settings().libpq_url, dbname="postgres")


def conninfo_for(dbname: str) -> str:
    return make_conninfo(get_settings().libpq_url, dbname=dbname)


def sqlalchemy_url_for(dbname: str) -> str:
    base, _, _ = get_settings().database_url.rpartition("/")
    return f"{base}/{dbname}"


def create_db(dbname: str, template: str | None = None) -> None:
    with psycopg.connect(admin_conninfo(), autocommit=True) as conn:
        stmt = sql.SQL("CREATE DATABASE {}").format(sql.Identifier(dbname))
        if template:
            stmt += sql.SQL(" TEMPLATE {}").format(sql.Identifier(template))
        conn.execute(stmt)


def drop_db(dbname: str) -> None:
    with psycopg.connect(admin_conninfo(), autocommit=True) as conn:
        conn.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(dbname))
        )


@contextmanager
def scratch_db(template: str | None = None) -> Iterator[str]:
    name = f"mona_scratch_{uuid.uuid4().hex[:12]}"
    create_db(name, template)
    try:
        yield name
    finally:
        drop_db(name)


def alembic(dbname: str, action: str, target: str) -> None:
    cfg = alembic_config()
    cfg.set_main_option("sqlalchemy.url", sqlalchemy_url_for(dbname).replace("%", "%%"))
    getattr(command, action)(cfg, target)


def pg_dump(dbname: str, *args: str) -> str:
    exe = os.environ.get("PG_DUMP") or shutil.which("pg_dump")
    assert exe, "pg_dump not found: install a PostgreSQL >= 17 client or set PG_DUMP"
    params = conninfo_to_dict(conninfo_for(dbname))
    env = {**os.environ, "PGPASSWORD": str(params.get("password", ""))}
    cmd = [
        exe,
        "--no-owner",
        "--no-privileges",
        "-h",
        str(params.get("host", "localhost")),
        "-p",
        str(params.get("port", 5432)),
        "-U",
        str(params["user"]),
        "-d",
        dbname,
        *args,
    ]
    for pattern in EXCLUDED_TABLES:
        cmd += ["-T", pattern]
    return subprocess.run(cmd, check=True, capture_output=True, text=True, env=env).stdout


def normalise_dump(dump: str) -> list[str]:
    lines = []
    for line in dump.splitlines():
        if not line.strip() or line.startswith("--") or re.match(r"\\(un)?restrict ", line):
            continue
        lines.append(line)
    return lines


def schema_dump(dbname: str) -> list[str]:
    return normalise_dump(pg_dump(dbname, "--schema-only"))

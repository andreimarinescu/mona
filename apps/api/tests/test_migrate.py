import psycopg
from psycopg.types.json import Jsonb

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


def test_0010_upgrades_a_0009_database_with_exports_and_cards_and_downgrades():
    from mona.ids import new_id
    from tests.pg import alembic, conninfo_for, scratch_db

    ent, pack, file, tab = new_id("ent"), new_id("exp"), new_id("exp"), new_id("exp")
    old_card, new_card = new_id("crd"), new_id("crd")
    card = (
        "INSERT INTO card_events (id, tool, kind, subject, channel) VALUES (%s, %s, %s, %s, 'web')"
    )
    with scratch_db() as db:
        alembic(db, "upgrade", "0009")
        with psycopg.connect(conninfo_for(db)) as conn:
            conn.execute(
                "INSERT INTO entities (id, key, display_name, folder_name)"
                " VALUES (%s, 'e', 'E', 'E')",
                (ent,),
            )
            conn.execute(
                "INSERT INTO exports (id, entity_id, fiscal_year, status, document_count)"
                " VALUES (%s, %s, 2025, 'ready', 4)",
                (pack, ent),
            )
            conn.execute(
                "INSERT INTO exports (id, status, document_count, format, title, file_path)"
                " VALUES (%s, 'ready', 2, 'xlsx', 'T', 't.xlsx')",
                (file,),
            )
            conn.execute(card, (old_card, "export_table", "export", Jsonb({"export_id": file})))
        alembic(db, "upgrade", "0010")
        with psycopg.connect(conninfo_for(db)) as conn:
            kept = conn.execute("SELECT id, format, spec FROM exports").fetchall()
            conn.execute(
                "INSERT INTO exports (id, status, document_count, format, title, spec)"
                " VALUES (%s, 'ready', 1, 'table', 'T', %s)",
                (tab, Jsonb({"columns": ["title"], "document_ids": [], "lang": "en"})),
            )
            conn.execute(card, (new_card, "export_table", "table", Jsonb({"export_id": tab})))
        alembic(db, "downgrade", "0009")
        with psycopg.connect(conninfo_for(db)) as conn:
            left = {r[0] for r in conn.execute("SELECT id FROM exports")}
            cards = [r[0] for r in conn.execute("SELECT id FROM card_events")]
    assert sorted(kept) == sorted([(pack, None, None), (file, "xlsx", None)])
    assert (left, cards) == ({pack, file}, [old_card])

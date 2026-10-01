"""D12: Hermes memory seeds rendered from the loaded registry, in the pinned store's format."""

from pathlib import Path

from sqlalchemy import create_engine, text
from typer.testing import CliRunner

from mona.demo import memory
from mona.settings import Settings
from tests.pg import scratch_db, sqlalchemy_url_for
from tests.pipeline_world import DEMO_SEED, OVERLAY


def entries(raw: str) -> list[str]:
    """The pinned Hermes `MemoryStore._parse_entries`."""
    return [e for e in (x.strip() for x in raw.split(memory.ENTRY_DELIMITER)) if e]


def test_the_demo_registry_renders_both_files(l1m2_demo_engine):
    with l1m2_demo_engine.connect() as conn:
        mem, user = memory.render(conn)
        again = memory.render(conn)
    assert (mem, user) == again
    for raw, limit in ((mem, memory.MEMORY_LIMIT), (user, memory.USER_LIMIT)):
        assert len(raw) <= limit and not raw.endswith("\n")
        assert memory.ENTRY_DELIMITER.join(entries(raw)) == raw
    m = entries(mem)
    assert m[0].startswith("Entities: Cabinet d'Orthodontie Dr Christine Simina (SELARL); ")
    assert "Medical Digital Design (SASU, fiscal year ends at the end of September)" in m[0]
    assert "LMNP (sub-unit Angers-Strasbourg)" in m[0]
    assert "Visitors" not in m[0] and "Personnel" not in m[0]
    assert m[1] == (
        "A personal household entity holds family papers, kept apart from the practice. Its"
        " documents never appear on Telegram or in an accountant pack."
    )
    assert m[2].startswith("Visitors holds documents volunteered by visitors")
    assert "removed after 24 hours" in m[2]
    assert m[3].startswith("The practice's accountants are OXYLEO and TALENZ.")
    u = entries(user)
    assert u[0] == "The owner is Claudiu Gamulescu (Claudiu). Claudiu runs the back office."
    assert u[1].startswith("Address Claudiu formally")
    assert u[2] == "Claudiu's interface language is English."


def test_the_memory_names_no_personal_entity_or_family_member(l1m2_demo_engine):
    """C9 §3.4: the memory is shared with Telegram, where personal entities are invisible."""
    with l1m2_demo_engine.connect() as conn:
        mem, _ = memory.render(conn)
        hidden = conn.execute(
            text("SELECT display_name, folder_name FROM entities WHERE visibility = 'personal'")
        ).all()
        family = conn.execute(
            text(
                "SELECT p.display_name, p.short_name FROM people p WHERE p.id IN"
                " (SELECT person_id FROM entity_people ep JOIN entities e ON e.id = ep.entity_id"
                "  WHERE e.visibility = 'personal')"
                " AND p.id NOT IN (SELECT person_id FROM entity_people ep JOIN entities e"
                "  ON e.id = ep.entity_id WHERE e.visibility = 'practice')"
            )
        ).all()
    names = {n for row in (*hidden, *family) for n in row if n}
    assert family and names
    assert [n for n in names if n in mem] == []


def test_a_registry_change_changes_the_rendering(l1m2_demo_engine):
    with l1m2_demo_engine.begin() as conn:
        conn.execute(text("UPDATE counterparties SET kind = 'insurer' WHERE kind = 'accountant'"))
        conn.execute(text("UPDATE profile SET name = 'Dr Christine Simina'"))
        mem, user = memory.render(conn)
    assert "The practice's accountant" not in mem
    owner = "Dr Christine Simina"
    assert entries(user)[0] == f"The owner is {owner}. {owner} runs the back office."


def test_write_replaces_both_files(l1m2_demo_engine, tmp_path):
    (tmp_path / "memories").mkdir()
    (tmp_path / "memories" / "MEMORY.md").write_text("hand-written")
    with l1m2_demo_engine.connect() as conn:
        paths = memory.write(conn, tmp_path)
        mem, user = memory.render(conn)
    assert [p.read_text(encoding="utf-8") for p in paths] == [mem, user]
    assert sorted(p.name for p in (tmp_path / "memories").iterdir()) == ["MEMORY.md", "USER.md"]


def test_seed_load_renders_the_memory_when_the_profile_is_mounted(tmp_path, monkeypatch):
    from mona.cli import app
    from tests.pg import alembic

    with scratch_db() as db:
        alembic(db, "upgrade", "head")
        url = sqlalchemy_url_for(db)
        settings = Settings(
            database_url=url, mona_owner_password="x", mona_hermes_home=tmp_path / "hermes"
        )
        engine = create_engine(url)
        monkeypatch.setattr("mona.settings.get_settings", lambda: settings)
        monkeypatch.setattr("mona.db.get_sync_engine", lambda: engine)
        try:
            res = CliRunner().invoke(
                app, ["seed", "load", str(DEMO_SEED), "--overlay", str(OVERLAY)]
            )
        finally:
            engine.dispose()
    assert res.exit_code == 0, res.output
    assert "rendered MEMORY.md, USER.md" in res.output
    user = Path(tmp_path / "hermes" / "memories" / "USER.md").read_text(encoding="utf-8")
    assert user.startswith("The owner is Claudiu Gamulescu (Claudiu).")


def test_an_empty_profile_setting_means_unset(monkeypatch):
    monkeypatch.setenv("MONA_HERMES_HOME", "")
    assert Settings(database_url="postgresql://x/y").mona_hermes_home is None


def test_the_seeds_hold_no_amount_iban_or_document_title(l1m2_demo_engine):
    import re

    with l1m2_demo_engine.connect() as conn:
        raw = "\n".join(memory.render(conn))
        titles = conn.execute(text("SELECT title FROM documents WHERE title IS NOT NULL")).scalars()
        assert not [t for t in titles if t in raw]
    assert not re.search(r"\d[\d  .,]*\s?(€|EUR|RON)", raw)
    assert not re.search(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){3,}", raw)

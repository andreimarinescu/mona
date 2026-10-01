import logging
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml
from argon2 import PasswordHasher
from sqlalchemy import create_engine, text
from typer.testing import CliRunner

from mona.iban import iban_hash
from mona.seed.files import SeedError
from mona.seed.loader import load_seed
from mona.seed.rules_export import dump_rules_yaml, export_rules
from mona.settings import Settings
from tests.pg import alembic, normalise_dump, pg_dump, scratch_db, sqlalchemy_url_for

FIXTURE = Path(__file__).parent / "fixtures" / "seed"
IBAN = "FR7630006000011234567890189"
IBAN_FORMS = [IBAN, "FR76 3000 6000 0112 3456 7890 189", IBAN.lower()]
PASSWORD = "correct horse battery staple"


@pytest.fixture(scope="module")
def template_db():
    with scratch_db() as db:
        alembic(db, "upgrade", "head")
        yield db


@pytest.fixture
def db(template_db):
    with scratch_db(template=template_db) as name:
        yield name


@pytest.fixture
def seed(tmp_path) -> Path:
    target = tmp_path / "seed"
    shutil.copytree(FIXTURE, target)
    return target


def settings_for(db: str, **kw) -> Settings:
    return Settings(database_url=sqlalchemy_url_for(db), mona_owner_password=PASSWORD, **kw)


def load(db: str, seed_dir: Path, *, overlay: Path | None | str = "default", **kw):
    engine = create_engine(sqlalchemy_url_for(db))
    try:
        with engine.begin() as conn:
            return load_seed(
                conn,
                seed_dir,
                settings=settings_for(db),
                overlay=seed_dir / "overlay.yaml" if overlay == "default" else overlay,
                **kw,
            )
    finally:
        engine.dispose()


def query(db: str, sql: str) -> list:
    engine = create_engine(sqlalchemy_url_for(db))
    try:
        with engine.connect() as conn:
            return list(conn.execute(text(sql)))
    finally:
        engine.dispose()


def full_dump(db: str) -> list[str]:
    return normalise_dump(pg_dump(db))


def edit(path: Path, change: Callable[[dict], None]) -> None:
    data = yaml.safe_load(path.read_text())
    change(data)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False))


def by_key(items: list[dict], key: str) -> dict:
    return next(i for i in items if i.get("key", i.get("id")) == key)


def test_loads_the_synthetic_seed(db, seed):
    summary = load(db, seed, tier="all")
    assert summary.inserted["rules"] == 6 and summary.inserted["entities"] == 5
    [(salt,)] = query(db, "SELECT iban_salt FROM settings")
    assert len(salt) == 32
    [(h, last4, sub)] = query(
        db,
        "SELECT a.iban_hash, a.iban_last4, s.key FROM accounts a"
        " JOIN sub_units s ON s.id = a.sub_unit_id",
    )
    assert (h, last4, sub) == (iban_hash(IBAN, bytes(salt)), "0189", "angers-strasbourg")
    [(pw,)] = query(db, "SELECT password_hash FROM profile")
    assert pw.startswith("$argon2id$") and PasswordHasher().verify(pw, PASSWORD)
    aliases = {a for (a,) in query(db, "SELECT alias_norm FROM counterparty_aliases")}
    assert {"agipi", "agipi assurance", "a.g.i.p.i.", "opco ep", "opco"} <= aliases
    [(fy_month, fy_day, siren)] = query(
        db, "SELECT fy_end_month, fy_end_day, siren FROM entities WHERE key = 'studio'"
    )
    assert (fy_month, fy_day, siren) == (9, 30, "888888880")
    [(name,)] = query(db, "SELECT display_name FROM people WHERE key = 'anna'")
    assert name == "Anna Marchand"
    [(ctext, prio, version)] = query(
        db, "SELECT condition_text, priority, version FROM rules WHERE key = 'hello-bank-lmnp'"
    )
    assert prio == 20 and version == 1
    assert ctext["en"] == (
        "When the counterparty is Hello bank and it shows the Hello bank · LMNP •• 0189 account."
    )
    assert query(db, "SELECT count(*) FROM rule_versions")[0][0] == 6
    assert query(db, "SELECT count(*) FROM templates WHERE entity_id IS NOT NULL")[0][0] == 1
    assert query(db, "SELECT sort_order FROM subcategories WHERE key = 'releve'")[0][0] == 10
    assert query(db, "SELECT sort_order FROM subcategories WHERE key = 'approbation'")[0][0] == 1


def test_stage_settings_load_from_the_practice_block(db, seed):
    load(db, seed)
    assert query(db, "SELECT debrief_early_min FROM settings")[0][0] == 5
    assert query(db, "SELECT auto_lock_minutes FROM profile")[0][0] == 15
    edit(seed / "practice.yaml", lambda d: d["practice"].update(
        debrief_early_min=7, auto_lock_minutes=120
    ))  # fmt: skip
    load(db, seed)
    assert query(db, "SELECT debrief_early_min FROM settings")[0][0] == 7
    assert query(db, "SELECT auto_lock_minutes FROM profile")[0][0] == 120


@pytest.mark.parametrize(
    "change", [{"debrief_early_min": 51}, {"debrief_early_min": 0}, {"auto_lock_minutes": 1441}]
)
def test_stage_settings_out_of_range_are_refused(db, seed, change):
    edit(seed / "practice.yaml", lambda d: d["practice"].update(change))
    with pytest.raises(SeedError):
        load(db, seed)
    assert query(db, "SELECT count(*) FROM settings")[0][0] == 0


def test_preseeded_tier_leaves_learned_rules_out(db, seed):
    load(db, seed)
    keys = {k for (k,) in query(db, "SELECT key FROM rules")}
    assert keys == {"opco-cabinet", "talenz-studio", "oxyleo-personal-tax", "unim-business"}


@pytest.mark.parametrize("tier", ["preseeded", "all"])
def test_loading_twice_leaves_an_identical_database(db, seed, tier):
    load(db, seed, tier=tier)
    first = full_dump(db)
    summary = load(db, seed, tier=tier)
    assert not summary.inserted and not summary.updated, summary
    assert full_dump(db) == first


def test_changed_rule_bumps_version_and_state_change_does_not(db, seed):
    load(db, seed)
    edit(seed / "rules.yaml", lambda d: by_key(d["rules"], "opco-cabinet")["conditions"].append(
        {"field": "text", "op": "contains", "value": "contribution"}))  # fmt: skip
    load(db, seed)
    edit(seed / "rules.yaml", lambda d: by_key(d["rules"], "opco-cabinet").update(state="disabled"))
    load(db, seed)
    [(version, prio, state)] = query(
        db, "SELECT version, priority, state FROM rules WHERE key = 'opco-cabinet'"
    )
    assert (version, prio, state) == (2, 20, "disabled")
    assert query(db, "SELECT count(*) FROM rule_versions v JOIN rules r ON r.id = v.rule_id"
                     " WHERE r.key = 'opco-cabinet'")[0][0] == 2  # fmt: skip


def test_rules_export_round_trips(db, seed):
    load(db, seed, tier="all")
    engine = create_engine(sqlalchemy_url_for(db))
    with engine.connect() as conn:
        exported = yaml.safe_load(dump_rules_yaml(export_rules(conn)))
    engine.dispose()
    assert exported["schema"] == "mona.rules/v1" and exported["revision"] == 6
    priorities = [r["priority"] for r in exported["rules"]]
    assert priorities == sorted(priorities, reverse=True)
    source = [
        r for name in ("rules.yaml", "rules.learned.yaml")
        for r in yaml.safe_load((seed / name).read_text())["rules"]
    ]  # fmt: skip
    defaults = {"state": "active", "source": "seed"}
    for rule in source:
        out = by_key(exported["rules"], rule["key"])
        expected = {**defaults, "priority": 10 * len(rule["conditions"]), **rule}
        assert {k: out[k] for k in expected} == expected
        assert set(out) - set(expected) == {"version", "condition_text", "stats"}
    (seed / "rules.yaml").write_text(dump_rules_yaml(exported))
    (seed / "rules.learned.yaml").write_text("schema: mona.rules/v1\nrules: []\n")
    before = full_dump(db)
    summary = load(db, seed, tier="all")
    assert not summary.updated and full_dump(db) == before


def test_iban_never_in_clear(db, seed, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    load(db, seed, tier="all")
    runner = CliRunner()
    monkeypatch.setattr("mona.settings.get_settings", lambda: settings_for(db))
    monkeypatch.setattr("mona.db.get_sync_engine", lambda: create_engine(sqlalchemy_url_for(db)))
    from mona.cli import app

    res = runner.invoke(
        app, ["seed", "load", str(seed), "--tier", "all", "--overlay", str(seed / "overlay.yaml")]
    )
    assert res.exit_code == 0, res.output
    engine = create_engine(sqlalchemy_url_for(db))
    with engine.connect() as conn:
        exported = dump_rules_yaml(export_rules(conn))
    engine.dispose()
    haystacks = {
        "data dump": pg_dump(db, "--data-only"),
        "log": caplog.text,
        "cli output": res.output,
        "rules export": exported,
    }
    for name, hay in haystacks.items():
        for form in IBAN_FORMS:
            assert form.upper() not in hay.upper(), f"IBAN in {name}"


def test_loader_never_touches_documents_journal_or_chat(db, seed):
    engine = create_engine(sqlalchemy_url_for(db))
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO batches (id, source) VALUES (:b, 'drop')"),
                     {"b": "bat_01j9zq3k8e6y4v2m7c5r1t0b01"})  # fmt: skip
        conn.execute(text(
            "INSERT INTO documents (id, sha256, original_name, mime_type, size_bytes, source,"
            " batch_id, location, current_path, status) VALUES (:d, :s, 'a.pdf',"
            " 'application/pdf', 1, 'drop', :b, 'inbox', 'a.pdf', 'processing')"),
            {"d": "doc_01j9zq3k8e6y4v2m7c5r1t0b01", "s": "f" * 64,
             "b": "bat_01j9zq3k8e6y4v2m7c5r1t0b01"})  # fmt: skip
        conn.execute(text("INSERT INTO file_ops (actor, via, action, undoable)"
                          " VALUES ('user', 'ui', 'doc.update', false)"))  # fmt: skip
        conn.execute(text("INSERT INTO conversations (id, title) VALUES (:c, 'hi')"),
                     {"c": "cnv_01j9zq3k8e6y4v2m7c5r1t0b01"})  # fmt: skip
    engine.dispose()
    tables = ["batches", "documents", "file_ops", "op_groups", "conversations", "chat_turns"]
    args = [a for t in tables for a in ("-t", t)]
    before = normalise_dump(pg_dump(db, "--data-only", *args))
    load(db, seed, tier="all")
    assert normalise_dump(pg_dump(db, "--data-only", *args)) == before


def _rule(d: dict, key: str) -> dict:
    return by_key(d["rules"], key)


def _cat(d: dict, key: str) -> dict:
    return by_key(d["categories"], key)


# (id, invariant, file, change); every case must fail the load and write nothing.
FAILING: list[tuple[str, int, str, Callable[[dict], None]]] = [
    ("rule-unknown-entity", 1, "rules.yaml",
     lambda d: _rule(d, "opco-cabinet")["action"].update(entity="selarl")),
    ("rule-unknown-person", 1, "rules.learned.yaml",
     lambda d: _rule(d, "hello-bank-lmnp")["conditions"].append(
         {"field": "person", "op": "mentions", "value": "zoe"})),
    ("account-unknown-sub-unit", 1, "practice.yaml",
     lambda d: d["accounts"][0].update(sub_unit="nantes")),
    ("sub-unit-unknown-person", 1, "practice.yaml",
     lambda d: by_key(d["entities"], "personal")["sub_units"][0].update(person="zoe")),
    ("template-unknown-entity", 1, "practice.yaml",
     lambda d: d["templates"][-1].update(entity="bakery")),
    ("unresolved-overlay-ref", 1, "practice.yaml",
     lambda d: by_key(d["entities"], "lmnp").update(siren={"ref": "entities.lmnp.siren"})),
    ("duplicate-rule-key", 1, "rules.learned.yaml",
     lambda d: _rule(d, "hello-bank-lmnp").update(key="opco-cabinet")),
    ("bad-key-slug", 1, "practice.yaml", lambda d: d["people"][1].update(key="Paul")),
    ("impossible-fiscal-year-end", 0, "practice.yaml",
     lambda d: by_key(d["entities"], "studio").update(fy_end_month=2, fy_end_day=30)),
    ("iban-literal-in-rules", 3, "rules.yaml",
     lambda d: _rule(d, "unim-business").update(name="UNIM FR7630006000011234567890189")),
    ("iban-literal-in-practice", 3, "practice.yaml",
     lambda d: d["accounts"][0].update(iban="FR76 3000 6000 0112 3456 7890 189")),
    ("category-missing-ro-label", 4, "practice.yaml",
     lambda d: _cat(d, "bank")["labels"].pop("ro")),
    ("subcategory-missing-fr-label", 4, "practice.yaml",
     lambda d: _cat(d, "tax")["subcategories"][0]["labels"].pop("fr")),
    ("icon-outside-ds-union", 4, "practice.yaml", lambda d: _cat(d, "bank").update(icon="coin")),
    ("path-template-unknown-token", 5, "practice.yaml",
     lambda d: d["templates"][0].update(path_template="{entity}/{amount}")),
    ("file-template-not-date-first", 5, "practice.yaml",
     lambda d: d["templates"][1].update(file_template="{counterparty}_{date:YYYY}")),
    ("rule-bad-op", 6, "rules.yaml",
     lambda d: _rule(d, "opco-cabinet")["conditions"][0].update(op="startswith")),
    ("rule-unit-without-entity", 6, "rules.learned.yaml",
     lambda d: _rule(d, "hello-bank-lmnp")["action"].pop("entity")),
    ("rule-visitors-entity", 6, "rules.yaml",
     lambda d: _rule(d, "opco-cabinet")["action"].update(entity="visitors")),
    ("two-default-templates", 7, "practice.yaml",
     lambda d: d["templates"].append({**d["templates"][0], "path_template": "{entity}/A"})),
    ("no-default-template", 7, "practice.yaml",
     lambda d: d["templates"].pop(4)),
]  # fmt: skip


@pytest.mark.parametrize(
    ("case", "invariant", "name", "change"), FAILING, ids=[c[0] for c in FAILING]
)
def test_every_invariant_rejects_its_failing_case(db, seed, case, invariant, name, change):
    edit(seed / name, change)
    with pytest.raises(SeedError) as e:
        load(db, seed, tier="all")
    assert invariant in {p.invariant for p in e.value.problems}, str(e.value)
    assert f"invariant {invariant} (" in str(e.value)
    for form in IBAN_FORMS:
        assert form not in str(e.value)
    assert query(db, "SELECT count(*) FROM entities")[0][0] == 0
    assert query(db, "SELECT count(*) FROM settings")[0][0] == 0


def test_unresolved_references_are_all_listed(db, seed):
    edit(seed / "rules.yaml", lambda d: [
        _rule(d, "opco-cabinet")["action"].update(entity="ghost-a"),
        _rule(d, "oxyleo-personal-tax")["action"].update(category="ghost_b"),
    ])  # fmt: skip
    with pytest.raises(SeedError) as e:
        load(db, seed, tier="all", overlay=None)
    messages = str(e.value)
    assert "'ghost-a'" in messages and "'ghost_b'" in messages
    assert "unresolved overlay reference 'iban.lmnp-hello' (no overlay loaded)" in messages


def test_failure_after_a_good_load_changes_nothing(db, seed):
    load(db, seed)
    before = full_dump(db)
    edit(seed / "rules.yaml", lambda d: _rule(d, "opco-cabinet")["action"].update(entity="x-y"))
    edit(seed / "practice.yaml", lambda d: d["people"][1].update(display_name="Paul M."))
    with pytest.raises(SeedError):
        load(db, seed)
    assert full_dump(db) == before


def test_cli_reports_the_invariant_and_exits_1(db, seed, monkeypatch):
    edit(seed / "practice.yaml", lambda d: _cat(d, "bank")["labels"].pop("ro"))
    monkeypatch.setattr("mona.settings.get_settings", lambda: settings_for(db))
    monkeypatch.setattr("mona.db.get_sync_engine", lambda: create_engine(sqlalchemy_url_for(db)))
    from mona.cli import app

    res = CliRunner().invoke(app, ["seed", "load", str(seed), "--overlay",
                                   str(seed / "overlay.yaml")])  # fmt: skip
    assert res.exit_code == 1
    assert "invariant 4 (complete labels): categories[bank].labels: missing ro label" in res.output

"""L1-M1 acceptance: C5 §8.5 paths on disk through apply_rule, undo byte-identical, seeds."""

import os
from datetime import date
from pathlib import Path

import pytest
import yaml
from sqlalchemy import create_engine, select, update

from mona.fileops import sha256_file
from mona.rules import store
from mona.seed.files import SeedError
from mona.seed.loader import import_rules, load_seed
from mona.seed.rules_export import dump_rules_yaml, export_rules
from mona.services import apply_rule, correct_document, undo
from mona.services.registry import T
from mona.settings import Settings
from tests.pg import alembic, normalise_dump, pg_dump, scratch_db, sqlalchemy_url_for
from tests.services_world import IBAN_SPACED, Services

REPO = Path(__file__).resolve().parents[3]
PRIVATE_OVERLAY = Path.home() / "DevFiles" / "mona-hq" / "demo-data" / "seed" / "identifiers.yaml"
AGIPI_VIE = {
    "schema": "mona.rules/v1",
    "rules": [
        {
            "key": "agipi-vie-by-person",
            "name": "AGIPI life insurance, filed under the insured person",
            "source": "interview",
            "state": "draft",
            "conditions": [
                {"field": "counterparty", "op": "equals", "value": "AGIPI"},
                {"field": "text", "op": "contains_any",
                 "value": ["assurance vie", "situation annuelle"]},
            ],
            "action": {"entity": "personal", "unit": {"from": "person"}, "category": "insurance",
                       "subcategory": "assurance_vie"},
        }
    ],
}  # fmt: skip

# C5 §8.5 rows: rule key, document values, path, file name.
CASES = {
    "1a": ("agipi-per-by-person",
           dict(counterparty="agipi", category="insurance", entity="personal",
                text="Votre plan d'épargne retraite AGIPI", addressee="M. Paul Marchand",
                doc_date=date(2025, 4, 14), reference="C-48213"),
           "Personnel/Paul/Assurances/AGIPI/PER/2025", "2025-04-14_AGIPI_PER_C-48213.pdf"),
    "1b": ("agipi-vie-by-person",
           dict(counterparty="agipi", category="insurance", entity="personal",
                text="Situation annuelle de votre assurance vie", addressee="Mme Anna Marchand",
                doc_date=date(2025, 3, 2)),
           "Personnel/Anna/Assurances/AGIPI/Assurance vie/2025",
           "2025-03-02_AGIPI_Assurance-vie.pdf"),
    "2": ("hello-bank-lmnp",
          dict(counterparty="hello-bank", category="bank", subcategory="releve", entity="lmnp",
               text=f"Relevé de compte IBAN {IBAN_SPACED}", period_start=date(2024, 12, 16),
               period_end=date(2025, 1, 15), doc_date=date(2025, 1, 16)),
          "LMNP/Angers-Strasbourg/Banque/2025", "2025-01-16_Hello-bank_Releve-de-compte.pdf"),
    "3": ("talenz-studio",
          dict(counterparty="talenz", category="annual_accounts", subcategory="approbation",
               entity="studio", text="Studio Numérique SIREN 888 888 880",
               period_end=date(2025, 9, 30), doc_date=date(2026, 1, 20)),
          "Studio Numérique/Documents annuels/2025",
          "2026-01-20_TALENZ_Approbation-des-comptes.pdf"),
    "4": ("oxyleo-personal-tax",
          dict(counterparty="oxyleo", category="tax", entity="personal",
               addressee="M. Paul Marchand", doc_date=date(2026, 5, 12)),
          "Personnel/Impôts et taxes/2026", "2026-05-12_OXYLEO_Elements-preparatoires.pdf"),
    "5": ("opco-cabinet",
          dict(counterparty="opco", category="payment_calls", entity="cabinet",
               period_end=date(2025, 12, 31), doc_date=date(2026, 2, 27), reference="2025-A-118"),
          "Cabinet Marchand/Appels de paiement/2025",
          "2026-02-27_OPCO_Contribution-OPCO_2025-A-118.pdf"),
    "6": ("unim-business",
          dict(counterparty="unim", category="insurance", subcategory="prevoyance",
               entity="cabinet", amount=120, doc_date=date(2025, 11, 3)),
          "Cabinet Marchand/Assurances/UNIM/Prévoyance/2025", "2025-11-03_UNIM_Prevoyance.pdf"),
    "7": ("talenz-studio",
          dict(counterparty="talenz", category="annual_accounts", subcategory="bilan",
               entity="studio", text="Bilan. SIREN 888 888 880", period_start=date(2024, 10, 1),
               period_end=date(2025, 9, 30), doc_date=date(2026, 1, 10)),
          "Studio Numérique/Documents annuels/2025", "2026-01-10_TALENZ_Bilan.pdf"),
}  # fmt: skip


@pytest.fixture
def s(seeded_engine, tmp_path) -> Services:
    w = Services(seeded_engine, tmp_path / "data")
    with seeded_engine.begin() as conn:
        cp = T["counterparties"]
        # §8.5 prints the OPCO counterparty's name as "OPCO"; the fixture seed says "OPCO EP".
        conn.execute(update(cp).where(cp.c.key == "opco").values(name="OPCO"))
    path = tmp_path / "agipi-vie.yaml"
    path.write_text(yaml.safe_dump(AGIPI_VIE, allow_unicode=True))
    with seeded_engine.begin() as conn:
        import_rules(conn, path)
    return w


def test_apply_rule_reproduces_the_c5_paths_and_undo_restores_every_byte(s):
    docs, originals = {}, {}
    for case, (_, values, _, _) in CASES.items():
        docs[case] = s.doc(**values)
        originals[case] = sha256_file(s.disk_path(docs[case]))
    groups = []
    for key in dict.fromkeys(rule for rule, *_ in CASES.values()):
        out = apply_rule(s.ctx, s.rule_id(key), actor="mona", via="chat")
        assert out.failed == [] and out.moved >= 1, key
        groups.append(out.group_id)
    archive = s.ctx.ops.roots.archive
    for case, (_, _, folder, name) in CASES.items():
        assert s.disk_path(docs[case]) == archive / folder / name, case
        assert sha256_file(archive / folder / name) == originals[case], case
    tree = {p.relative_to(archive).as_posix() for p in archive.rglob("*") if p.is_file()}
    assert tree == {f"{folder}/{name}" for _, _, folder, name in CASES.values()}
    for g in reversed(groups):
        u = undo(s.ctx, actor="mona", via="chat", group_id=g)
        assert u.skipped == []
    inbox = s.ctx.ops.roots.inbox
    for case, doc in docs.items():
        assert s.disk_path(doc) == inbox / f"{doc}.pdf", case
        assert sha256_file(inbox / f"{doc}.pdf") == originals[case], case
        assert s.row(doc)["status"] == "review"
    assert [p for p in archive.rglob("*") if p.is_file()] == []


def test_six_feedback_cases_through_corrections_and_scope_all(s):
    doc = s.doc(**CASES["4"][1])
    out = correct_document(s.ctx, doc, actor="mona", via="chat", entity="personal",
                           category="tax", subcategory="preparation")  # fmt: skip
    folder, name = CASES["4"][2:]
    assert s.disk_path(doc) == s.ctx.ops.roots.archive / folder / name
    assert out.document.sub_unit_id is None


def test_demo_seed_loads_with_the_overlay():
    overlay = Path(os.environ.get("MONA_SEED_OVERLAY") or PRIVATE_OVERLAY)
    if not overlay.is_file():
        pytest.skip("private identifier overlay not present")
    with scratch_db() as db:
        alembic(db, "upgrade", "head")
        url = sqlalchemy_url_for(db)
        engine = create_engine(url)
        settings = Settings(database_url=url, mona_owner_password="x" * 12)
        try:
            for expected in ("+", "no changes"):
                with engine.begin() as conn:
                    summary = load_seed(conn, REPO / "demo" / "seed", settings=settings,
                                        tier="preseeded", overlay=overlay)  # fmt: skip
                assert expected in str(summary)
        finally:
            engine.dispose()


# --- rules.yaml (C5 §10, §11 test 15) ---


def test_rules_import_round_trips(seeded_engine, tmp_path):
    with seeded_engine.connect() as conn:
        exported = dump_rules_yaml(export_rules(conn))
    (tmp_path / "rules.yaml").write_text(exported)
    url = seeded_engine.url.render_as_string(hide_password=False)
    db = url.rpartition("/")[2]
    before = normalise_dump(pg_dump(db, "--data-only"))
    with seeded_engine.begin() as conn:
        summary = import_rules(conn, tmp_path / "rules.yaml")
    assert "no changes" in str(summary)
    assert normalise_dump(pg_dump(db, "--data-only")) == before


def test_rules_import_upserts_and_bumps_versions(seeded_engine, tmp_path):
    doc = {"schema": "mona.rules/v1", "rules": [
        {"key": "opco-cabinet", "name": "OPCO", "priority": 25,
         "conditions": [{"field": "counterparty", "op": "equals", "value": "OPCO"}],
         "action": {"entity": "cabinet", "category": "payment_calls"}}]}  # fmt: skip
    (tmp_path / "r.yaml").write_text(yaml.safe_dump(doc))
    with seeded_engine.begin() as conn:
        t = T["rules"]
        conn.execute(update(t).where(t.c.key == "opco-cabinet").values(corrections_since=3))
        import_rules(conn, tmp_path / "r.yaml")
        row = conn.execute(select(t).where(t.c.key == "opco-cabinet")).mappings().one()
        n = conn.execute(select(t)).all()
    assert (row["version"], row["priority"], row["corrections_since"]) == (2, 25, 0)
    assert len(n) == 6


@pytest.mark.parametrize("where", ["value", "name"])
def test_rules_import_rejects_a_clear_iban(seeded_engine, tmp_path, where):
    iban = "FR7630006000011234567890189"
    rule = {
        "key": "x",
        "name": "x",
        "conditions": [{"field": "text", "op": "contains", "value": "y"}],
        "action": {"entity": "cabinet"},
    }
    if where == "value":
        rule["conditions"][0]["value"] = f"IBAN {iban}"
    else:
        rule["name"] = f"account {iban}"
    (tmp_path / "r.yaml").write_text(yaml.safe_dump({"schema": "mona.rules/v1", "rules": [rule]}))
    with seeded_engine.begin() as conn, pytest.raises(SeedError) as err:
        import_rules(conn, tmp_path / "r.yaml")
    assert "invariant 3" in str(err.value) and iban not in str(err.value)


def test_export_rewrites_the_config_file_and_keeps_history(seeded_engine, tmp_path):
    with seeded_engine.begin() as conn:
        first = store.write_export(conn, tmp_path)
        rev = yaml.safe_load(first.read_text())["revision"]
        t = T["rules"]
        conn.execute(update(t).where(t.c.key == "opco-cabinet").values(state="disabled"))
        store.write_export(conn, tmp_path)
    assert (tmp_path / "rules.history" / f"rules-{rev}.yaml").read_text() != first.read_text()
    assert "state: disabled" in first.read_text()
    assert not list(tmp_path.glob("*.tmp"))


def test_rule_statistics(s):
    doc = s.doc(**CASES["5"][1])
    rid = s.rule_id("opco-cabinet")
    apply_rule(s.ctx, rid, actor="mona", via="chat")
    correct_document(s.ctx, doc, actor="mona", via="chat", entity="studio")
    with s.engine.connect() as conn:
        r = conn.execute(select(T["rules"]).where(T["rules"].c.id == rid)).mappings().one()
    assert (r["fired_count"], r["corrections_since"]) == (1, 1)
    assert r["last_fired_at"] == s.clock()

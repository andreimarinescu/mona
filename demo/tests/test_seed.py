import copy
import re
from datetime import date
from pathlib import Path

import pytest
import rules_schema
import templates
import textnorm
import yaml

DEMO = Path(__file__).resolve().parents[1]
ROOT = DEMO.parent
ICONS = {"bank", "invoice", "tax", "insurance", "payroll", "training", "travel", "personal"}
CATEGORY_IDS = {
    "annual_accounts",
    "payment_calls",
    "supplier_invoices",
    "misc_expenses",
    "sales_invoices",
    "bank",
    "payroll",
    "insurance",
    "training",
    "travel",
    "tax",
    "health",
    "patient_documents",
    "general",
}
KEY = re.compile(r"^[a-z][a-z0-9-]{1,39}$")
MAX_DAY = {2: 28, 4: 30, 6: 30, 9: 30, 11: 30}
PRESEEDED = {
    "opco-selarl",
    "talenz-mdd",
    "selarl-annual-accounts",
    "oxyleo-personal-tax",
    "unim-business",
    "payroll-selarl",
}
LEARNED = {"agipi-per-by-person", "agipi-assurance-vie-by-person", "hello-bank-lmnp"}


def contract_definitions() -> dict[str, str]:
    text = (ROOT / "docs" / "contracts" / "C5-classification.md").read_text(encoding="utf-8")
    section = text.split("### 5.6 Category definitions")[1].split("`health` is new")[0]
    out = {}
    for line in section.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.startswith("|") and len(cells) == 3 and cells[1].startswith("`") and "unknown" not in cells[1]:
            out[cells[1].strip("`").split()[0]] = cells[2]
    return out


def test_practice_keys_and_entities(practice):
    assert {p["key"] for p in practice["people"]} == {"claudiu", "christine", "child-1", "child-2"}
    keys = [e["key"] for e in practice["entities"]]
    assert len(keys) == len(set(keys)) and all(KEY.match(k) for k in keys)
    assert len({e["folder_name"] for e in practice["entities"]}) == len(keys)
    visitors = [e for e in practice["entities"] if e.get("purge_after_hours")]
    assert [e["key"] for e in visitors] == ["visitors"]
    for e in practice["entities"]:
        assert e["visibility"] in {"practice", "personal"} and e["filing_language"] == "fr"
        date(2024, e["fy_end_month"], e["fy_end_day"])
        assert e["fy_end_day"] <= MAX_DAY.get(e["fy_end_month"], 31)


def test_sub_units_and_people_links(practice):
    people = {p["key"] for p in practice["people"]}
    entities = {e["key"]: e for e in practice["entities"]}
    assert [u["key"] for u in entities["lmnp"]["sub_units"]] == ["angers-strasbourg"]
    assert {u["person"] for u in entities["personal"]["sub_units"]} == people
    for e in entities.values():
        unit_keys = [u["key"] for u in e.get("sub_units", [])]
        assert len(unit_keys) == len(set(unit_keys))
        assert {p["person"] for p in e.get("people", [])} <= people
        for unit in e.get("sub_units", []):
            assert unit.get("person", next(iter(people))) in people


def test_categories_follow_c5_5_6(practice):
    cats = {c["id"]: c for c in practice["categories"]}
    assert set(cats) == CATEGORY_IDS
    definitions = contract_definitions()
    assert set(definitions) == CATEGORY_IDS
    for cid, c in cats.items():
        assert c["model_definition"] == definitions[cid]
        assert c["icon"] in ICONS
        assert set(c["labels"]) == {"en", "fr", "ro"} and all(c["labels"].values())
        sub_keys = [s["key"] for s in c["subcategories"]]
        assert sub_keys and len(sub_keys) == len(set(sub_keys))
        for s in c["subcategories"]:
            assert re.match(r"^[a-z][a-z0-9_]{0,39}$", s["key"])
            assert set(s["labels"]) == {"en", "fr", "ro"} and all(s["labels"].values())
    assert cats["health"]["icon"] == "personal"


def test_one_default_template_per_category_and_all_parse(practice):
    defaults = [t["category"] for t in practice["templates"] if "entity" not in t]
    assert sorted(defaults) == sorted(CATEGORY_IDS)
    for t in practice["templates"]:
        templates.parse(t["path_template"], "path")
        templates.parse(t["file_template"], "file")


def test_counterparties_and_accounts(practice):
    cps = practice["counterparties"]
    assert len({c["key"] for c in cps}) == len(cps) and all(KEY.match(c["key"]) for c in cps)
    norms = [textnorm.norm(c["name"]) for c in cps]
    assert len(norms) == len(set(norms))
    owners: dict[str, str] = {}
    for c in cps:
        for a in [c["name"], *c["aliases"]]:
            assert owners.setdefault(textnorm.norm(a), c["key"]) == c["key"], f"alias {a} belongs to two counterparties"
    entities = {e["key"]: e for e in practice["entities"]}
    cp_keys = {c["key"] for c in cps}
    raw = yaml.safe_load((DEMO / "seed" / "practice.yaml").read_text(encoding="utf-8"))
    for a in raw["accounts"]:
        assert a["entity"] in entities and a["bank_counterparty"] in cp_keys
        assert a["sub_unit"] in {u["key"] for u in entities[a["entity"]]["sub_units"]}
        assert set(a["iban"]) == {"ref"} and a["currency"] in {"EUR", "RON"}


def test_refs_resolve_against_the_overlay(overlay):
    if overlay is None:
        pytest.skip("private overlay not available")
    raw = yaml.safe_load((DEMO / "seed" / "practice.yaml").read_text(encoding="utf-8"))
    refs: list[str] = []

    def walk(node):
        if isinstance(node, dict):
            refs.extend([node["ref"]] if set(node) == {"ref"} else [])
            [walk(v) for v in node.values()]
        elif isinstance(node, list):
            [walk(v) for v in node]

    walk(raw)
    assert refs
    for ref in refs:
        assert templates.resolve_refs({"ref": ref}, overlay) not in (None, []), ref


@pytest.mark.parametrize("name", ["rules.yaml", "rules.learned.yaml"])
def test_rules_files_validate(practice, name):
    assert rules_schema.validate(templates.load_rules(name), practice) == []


def test_tiers_are_disjoint_and_complete():
    seeded = {r["key"] for r in templates.load_rules()["rules"]}
    learned = {r["key"] for r in templates.load_rules("rules.learned.yaml")["rules"]}
    assert seeded == PRESEEDED and learned == LEARNED and not seeded & learned
    for r in templates.load_rules()["rules"]:
        assert r["source"] == "seed" and "unit" not in r["action"]
    for r in templates.load_rules("rules.learned.yaml")["rules"]:
        assert r["source"] == "interview"


def test_person_splits_exist_only_through_learned_rules(practice):
    units = [r for r in templates.load_rules("rules.learned.yaml")["rules"] if "unit" in r["action"]]
    assert {r["key"] for r in units} == LEARNED
    assert [r["key"] for r in units if r["action"]["unit"] == {"from": "person"}] == [
        "agipi-per-by-person",
        "agipi-assurance-vie-by-person",
    ]


def _mutated(rule_patch):
    doc = copy.deepcopy(templates.load_rules())
    rule_patch(doc["rules"][0])
    return doc


@pytest.mark.parametrize(
    ("patch", "needle"),
    [
        (
            lambda r: r["conditions"].__setitem__(0, {"field": "counterparty", "op": "starts", "value": "opco-ep"}),
            "bad field/op",
        ),
        (
            lambda r: r["conditions"].__setitem__(0, {"field": "counterparty", "op": "equals", "value": "nobody"}),
            "unresolved",
        ),
        (lambda r: r["action"].update(entity="visitors"), "Visitors"),
        (lambda r: r["action"].update(unit="nowhere"), "unknown sub-unit"),
        (lambda r: r["action"].update(subcategory="per"), "not under"),
        (lambda r: r["action"].update(path="{entity}/{nope}"), "unknown token"),
        (lambda r: r.update(conditions=[r["conditions"][0]] * 9), "1 to 8 conditions"),
        (
            lambda r: r["conditions"].append({"field": "text", "op": "contains", "value": "FR" + "76" + "1" * 23}),
            "IBAN literal",
        ),
        (lambda r: r["conditions"].append({"field": "siren", "op": "equals", "value": "12345"}), "9 digits"),
        (lambda r: r.update(state="paused"), "bad state"),
    ],
)
def test_validator_rejects_bad_rules(practice, patch, needle):
    errors = rules_schema.validate(_mutated(patch), practice)
    assert any(needle in e for e in errors), errors


def test_every_category_renders_for_every_entity(practice):
    reg = templates.Registry.from_practice(practice)
    for cid, cat in reg.categories.items():
        for key in reg.entities:
            doc = templates.Doc(
                entity=key,
                category=cid,
                subcategory=cat["subcategories"][0]["key"],
                counterparty="Exemple SA",
                reference="REF-1",
                doc_date=date(2026, 10, 14),
                arrived_on=date(2026, 10, 20),
            )
            out = templates.render(reg, doc)
            assert "{" not in out.path and "{" not in out.file_name and out.file_name.startswith("2026-10-14_")
            assert out.file_name.isascii() and "__" not in out.file_name

from datetime import date

import pytest
import templates
import yaml

PRACTICE = templates.load_practice()
RULES = templates.load_rules()
DOCS = yaml.safe_load((templates.SEED_DIR.parent / "synthetic" / "docs.yaml").read_text(encoding="utf-8"))
ICONS = {"bank", "invoice", "tax", "insurance", "payroll", "training", "travel", "personal"}
ENTITIES = {e["id"]: e for e in PRACTICE["entities"]}
CATEGORIES = {c["id"]: c for c in PRACTICE["categories"]}


def test_entities_are_well_formed():
    assert len(ENTITIES) == len(PRACTICE["entities"])
    for e in ENTITIES.values():
        assert e["visibility"] in {"practice", "personal"}
        assert e["filing_language"] == "fr"
        if e["fiscal_year_end"] is None:
            assert "fiscal_year_end_todo" in e
        else:
            month, day = (int(p) for p in e["fiscal_year_end"].split("-"))
            date(2024, month, day)


def test_categories_are_well_formed():
    assert len(CATEGORIES) == len(PRACTICE["categories"])
    for c in CATEGORIES.values():
        assert c["icon"] in ICONS
        assert set(c["labels"]) == {"fr", "en", "ro"}
        assert templates.template_tokens(c["path_template"]) <= templates.TOKENS
        assert templates.template_tokens(c["file_template"]) <= templates.TOKENS


@pytest.mark.parametrize("category", sorted(CATEGORIES))
def test_every_category_renders_without_unknown_tokens(category):
    meta = {
        "entity": "selarl-simina",
        "category": category,
        "subcategory": "Facture",
        "counterparty": "Exemple SA",
        "issuer": "Exemple SA",
        "reference": "REF-1",
    }
    path = templates.render_path(PRACTICE, meta, date(2026, 10, 14))
    name = templates.render_file_name(PRACTICE, meta, date(2026, 10, 14))
    assert "{" not in path and "}" not in path and "//" not in path and path
    assert "{" not in name and "__" not in name and name.startswith("2026-10-14_") and name.endswith(".pdf")
    assert name.isascii() and " " not in name


def test_unknown_token_is_rejected():
    bad = {
        "categories": [
            {"id": "x", "path_template": "{entity}/{nope}", "labels": {"fr": "X"}, "file_template": "{date}"}
        ],
        "entities": PRACTICE["entities"],
        "practice": PRACTICE["practice"],
    }
    with pytest.raises(ValueError):
        templates.render_path(bad, {"entity": "mdd", "category": "x"}, date(2026, 1, 1))


def test_folders_keep_accents_and_file_names_drop_them():
    meta = {"entity": "personal", "category": "tax", "subcategory": "Éléments préparatoires", "issuer": "OXYLEO"}
    assert templates.render_path(PRACTICE, meta, date(2026, 10, 11)) == "Personnel/Impôts et taxes/2026"
    assert (
        templates.render_file_name(PRACTICE, meta, date(2026, 10, 11)) == "2026-10-11_OXYLEO_Elements-preparatoires.pdf"
    )


@pytest.mark.parametrize(
    ("period_end", "fy_end", "expected"),
    [
        (date(2024, 9, 30), "09-30", 2024),
        (date(2024, 10, 1), "09-30", 2025),
        (date(2025, 1, 15), "12-31", 2025),
        (date(2025, 1, 15), None, 2025),
        (date(2024, 12, 31), "12-31", 2024),
    ],
)
def test_fiscal_year(period_end, fy_end, expected):
    assert templates.fiscal_year(period_end, fy_end) == expected


def test_lmnp_bank_statement_lands_in_sub_unit_folder():
    meta = {
        "entity": "lmnp",
        "sub_unit": "angers-strasbourg",
        "category": "bank",
        "subcategory": "Relevé de compte",
        "counterparty": "Hello bank",
    }
    assert (
        templates.render_path(PRACTICE, meta, date(2025, 3, 15), date(2025, 3, 15))
        == "LMNP/Angers-Strasbourg/Banque/2025"
    )


def test_rules_reference_known_entities_categories_and_units():
    rules = RULES["rules"]
    assert len({r["id"] for r in rules}) == len(rules)
    for r in rules:
        assert r["conditions"] and r["condition_text"] and r["source"] == "seed"
        for cond in r["conditions"]:
            assert ("value" in cond) ^ ("ref" in cond)
            if "ref" in cond:
                assert cond["ref"].startswith("identifiers.")
        action = r["action"]
        assert action["entity"] in ENTITIES and action["category"] in CATEGORIES
        unit = action.get("sub_unit")
        if isinstance(unit, str):
            assert unit in {u["id"] for u in ENTITIES[action["entity"]]["sub_units"]}
        if "subcategory" in action:
            assert action["subcategory"] in CATEGORIES[action["category"]]["subcategories"]


def test_seed_rules_cover_the_six_feedback_cases():
    ids = {r["id"] for r in RULES["rules"]}
    assert {
        "seed-agipi-per-by-insured",
        "seed-agipi-life-by-insured",
        "seed-hello-bank-lmnp",
        "seed-talenz-mdd",
        "seed-oxyleo-personal-tax",
        "seed-opco-selarl",
        "seed-unim-business",
    } <= ids


@pytest.mark.parametrize("doc", [d for d in DOCS["docs"] if "path" in d.get("expected", {})], ids=lambda d: d["id"])
def test_synthetic_expected_path_and_name_match_the_templates(doc):
    exp = doc["expected"]
    anchor = DOCS["reference_anchor"]
    dates = {k: templates_date(v, anchor) for k, v in doc["dates"].items()}
    meta = {
        "entity": exp["entity"],
        "sub_unit": exp.get("sub_unit"),
        "category": exp["category"],
        "subcategory": exp["subcategory"],
        "counterparty": exp["counterparty"],
        "issuer": exp.get("issuer", ""),
        "reference": doc.get("reference", ""),
    }
    ext = exp["file_name"].rsplit(".", 1)[1]
    assert templates.render_path(PRACTICE, meta, dates["doc"], dates.get("period_end")) == exp["path"]
    assert templates.render_file_name(PRACTICE, meta, dates["doc"], ext) == exp["file_name"]


def templates_date(spec, anchor):
    from datetime import timedelta

    if "offset" in spec:
        return anchor + timedelta(days=spec["offset"])
    dy, month, day = spec["ym"]
    return date(anchor.year + dy, month, day)


def test_empty_tokens_drop_their_path_segment_and_file_name_part():
    meta = {"entity": "personal", "category": "insurance", "counterparty": "MAE", "reference": "R-1"}
    assert templates.render_path(PRACTICE, meta, date(2025, 8, 31)) == "Personnel/Assurances/MAE/2025"
    assert templates.render_file_name(PRACTICE, meta, date(2025, 8, 31)) == "2025-08-31_MAE_R-1.pdf"

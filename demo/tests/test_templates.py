from datetime import date
from pathlib import Path

import pytest
import templates
import yaml

EXAMPLES = yaml.safe_load((Path(__file__).parent / "c5_examples.yaml").read_text(encoding="utf-8"))
REG = templates.Registry.from_practice(EXAMPLES)
ARRIVED = date(2026, 10, 20)


def doc_from(spec: dict) -> templates.Doc:
    return templates.Doc(arrived_on=ARRIVED, **spec)


@pytest.mark.parametrize("case", EXAMPLES["cases"], ids=lambda c: f"8.5-case-{c['id']}")
def test_c5_worked_examples(case):
    out = templates.render(REG, doc_from(case["doc"]))
    assert out.path == case["path"]
    if "file_name" in case:
        assert out.file_name == case["file_name"]


@pytest.mark.parametrize(
    ("template", "kind", "offset"),
    [
        ("{entity}/{nope}", "path", 10),
        ("{entity}/{sub:YYYY}", "path", 13),
        ("{entity}/{date:YYYY-XX}", "path", 20),
        ("{date:}_{sub}", "file", 6),
        ("{entity}/{year", "path", 9),
        ("{entity}/year}", "path", 13),
        ("{entity}//{year}", "path", 9),
        ("/{entity}", "path", 0),
        ("{entity}/", "path", 9),
        ("{entity}/../{year}", "path", 9),
        ("{counterparty}_{date:YYYY}", "file", 0),
        ("{date:YYYY}/{sub}", "file", 11),
        ("{date:YYYY}_{sub}.pdf", "file", 17),
    ],
)
def test_grammar_errors_carry_an_offset(template, kind, offset):
    with pytest.raises(templates.TemplateError) as exc:
        templates.parse(template, kind)
    assert exc.value.offset == offset


def test_valid_templates_parse():
    assert templates.parse("{entity}/{fy} {entity}/Documents annuels", "path")
    assert templates.parse("{date:YY.MM.DD}_{reference}", "file")


def test_empty_reference_leaves_no_double_separator():
    doc = doc_from(
        dict(
            entity="cabinet", category="insurance", subcategory="per", counterparty="AGIPI", doc_date=date(2025, 4, 14)
        )
    )
    assert templates.render(REG, doc).file_name == "2025-04-14_AGIPI_PER.pdf"


def test_empty_tokens_drop_their_segment_and_their_separator():
    doc = doc_from(
        {
            "entity": "cabinet",
            "category": "insurance",
            "counterparty": "AGIPI",
            "reference": "C-48213",
            "doc_date": date(2025, 4, 14),
        }
    )
    out = templates.render(REG, doc)
    assert out.path == "Cabinet Marchand/Assurances/AGIPI/2025"
    assert out.file_name == "2025-04-14_AGIPI_C-48213.pdf"


def test_stem_is_capped_at_116_characters_on_a_separator():
    doc = doc_from(
        dict(
            entity="cabinet",
            category="insurance",
            subcategory="per",
            counterparty=" ".join(["Mutuelle"] * 30),
            reference="R" * 30,
            doc_date=date(2025, 4, 14),
        )
    )
    stem = templates.render(REG, doc).file_name.removesuffix(".pdf")
    assert len(stem) <= 116 and not stem.endswith(("-", "_"))
    assert stem.startswith("2025-04-14_Mutuelle-Mutuelle")


def test_long_folder_segment_is_cut_on_a_character_boundary():
    doc = doc_from(
        dict(entity="cabinet", category="insurance", counterparty="\U0001f9b7" * 80, doc_date=date(2025, 4, 14))
    )
    segment = templates.render(REG, doc).path.split("/")[2]
    assert len(segment.encode("utf-8")) <= 255 and segment == "\U0001f9b7" * 63


def test_unsafe_characters_never_split_a_segment():
    assert templates.folder_segment("AXA / AGIPI: a*b?") == "AXA - AGIPI- a-b-"
    assert templates.folder_segment("  ..x.. ") == "x"


def test_rendering_is_deterministic():
    case = EXAMPLES["cases"][0]
    assert templates.render(REG, doc_from(case["doc"])) == templates.render(REG, doc_from(case["doc"]))


def test_entity_inside_a_longer_segment_renders_the_folder_only():
    doc = doc_from(
        dict(
            entity="personal",
            unit="anna",
            category="bank",
            period_end=date(2025, 12, 31),
            path_template="{entity}/{fy} {entity}",
        )
    )
    assert templates.render(REG, doc).path == "Personnel/Anna/2025 Personnel"


@pytest.mark.parametrize(
    ("d", "fy_end", "expected"),
    [
        (date(2025, 9, 30), (9, 30), 2025),
        (date(2025, 10, 1), (9, 30), 2026),
        (date(2026, 3, 31), (9, 30), 2026),
        (date(2025, 12, 31), (12, 31), 2025),
        (date(2026, 1, 1), (12, 31), 2026),
        (date(2025, 2, 28), (2, 28), 2025),
        (date(2025, 3, 1), (2, 28), 2026),
    ],
)
def test_fiscal_year_boundaries(d, fy_end, expected):
    assert templates.fiscal_year(d, *fy_end) == expected


def test_fallbacks_and_penalties_follow_8_2():
    base = dict(entity="studio", category="annual_accounts", subcategory="bilan", counterparty="TALENZ")
    out = templates.render(REG, doc_from(base | dict(doc_date=date(2026, 1, 20), period_end=date(2025, 9, 30))))
    assert (out.penalty, out.fiscal_year) == (0, 2025)
    out = templates.render(REG, doc_from(base | dict(doc_date=date(2026, 1, 20))))
    assert (out.path, out.penalty, out.fiscal_year) == ("Studio Numérique/Documents annuels/2026", 10, 2026)
    out = templates.render(REG, doc_from(base))
    assert (out.file_name, out.penalty) == ("2026-10-20_TALENZ_Bilan.pdf", 40)
    year = templates.render(
        REG, doc_from(dict(entity="personal", category="tax", subcategory="preparation", period_end=date(2024, 12, 31)))
    )
    assert year.path == "Personnel/Impôts et taxes/2024" and year.penalty == 30


def test_fiscal_year_is_computed_for_year_templated_documents():
    doc = doc_from(dict(entity="studio", category="tax", doc_date=date(2025, 10, 1)))
    assert templates.render(REG, doc).fiscal_year == 2026


def test_file_extension_follows_the_mime_type():
    doc = doc_from(dict(entity="cabinet", category="bank", doc_date=date(2025, 1, 1), mime_type="image/jpeg"))
    assert templates.render(REG, doc).file_name.endswith(".jpg")

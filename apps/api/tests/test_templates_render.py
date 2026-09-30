from datetime import UTC, date, datetime

import pytest

from mona.templates import (
    EntityInfo,
    NotRenderable,
    RenderValues,
    document_fiscal_year,
    file_stem,
    fiscal_year,
    folder_segment,
    render,
    slug,
)
from tests.c5_registry import CATEGORIES, TEMPLATES, values

CASES = [
    (
        "1a",
        values(
            "personal", "insurance", unit="paul", subcategory="per", counterparty="AGIPI",
            reference="C-48213", doc_date=date(2025, 4, 14),
        ),
        "Personnel/Paul/Assurances/AGIPI/PER/2025",
        "2025-04-14_AGIPI_PER_C-48213.pdf",
    ),
    (
        "1b",
        values(
            "personal", "insurance", unit="anna", subcategory="assurance_vie",
            counterparty="AGIPI", doc_date=date(2025, 3, 2),
        ),
        "Personnel/Anna/Assurances/AGIPI/Assurance vie/2025",
        "2025-03-02_AGIPI_Assurance-vie.pdf",
    ),
    (
        "2",
        values(
            "lmnp", "bank", unit="angers-strasbourg", subcategory="releve",
            counterparty="Hello bank", doc_date=date(2025, 1, 16), period_end=date(2025, 1, 15),
        ),
        "LMNP/Angers-Strasbourg/Banque/2025",
        "2025-01-16_Hello-bank_Releve-de-compte.pdf",
    ),
    (
        "3",
        values(
            "studio", "annual_accounts", subcategory="approbation", counterparty="TALENZ",
            doc_date=date(2026, 1, 20), period_end=date(2025, 9, 30),
        ),
        "Studio Numérique/Documents annuels/2025",
        "2026-01-20_TALENZ_Approbation-des-comptes.pdf",
    ),
    (
        "4",
        values(
            "personal", "tax", subcategory="preparation", counterparty="OXYLEO",
            doc_date=date(2026, 5, 12),
        ),
        "Personnel/Impôts et taxes/2026",
        "2026-05-12_OXYLEO_Elements-preparatoires.pdf",
    ),
    (
        "5",
        values(
            "cabinet", "payment_calls", subcategory="contribution_opco", counterparty="OPCO",
            reference="2025-A-118", doc_date=date(2026, 2, 27), period_end=date(2025, 12, 31),
        ),
        "Cabinet Marchand/Appels de paiement/2025",
        "2026-02-27_OPCO_Contribution-OPCO_2025-A-118.pdf",
    ),
    (
        "6",
        values(
            "cabinet", "insurance", subcategory="prevoyance", counterparty="UNIM",
            doc_date=date(2025, 11, 3),
        ),
        "Cabinet Marchand/Assurances/UNIM/Prévoyance/2025",
        "2025-11-03_UNIM_Prevoyance.pdf",
    ),
    (
        "7",
        values(
            "studio", "annual_accounts", subcategory="bilan", counterparty="TALENZ",
            doc_date=date(2026, 1, 10), period_end=date(2025, 9, 30),
        ),
        "Studio Numérique/Documents annuels/2025",
        "2026-01-10_TALENZ_Bilan.pdf",
    ),
    (
        "8",
        values(
            "cabinet", "insurance", subcategory="prevoyance", counterparty="AXA / AGIPI",
            reference="N° 77/12", doc_date=date(2025, 6, 1),
        ),
        "Cabinet Marchand/Assurances/AXA - AGIPI/Prévoyance/2025",
        "2025-06-01_AXA-AGIPI_Prevoyance_N-77-12.pdf",
    ),
]  # fmt: skip


@pytest.mark.parametrize(("case", "v", "path", "file_name"), CASES, ids=[c[0] for c in CASES])
def test_c5_worked_examples(case, v, path, file_name):
    out = render(*TEMPLATES[_category_of(v)], v)
    assert (out.folder, out.file_name) == (path, file_name)
    assert out.penalty == 0


def _category_of(v: RenderValues) -> str:
    return next(k for k, labels in CATEGORIES.items() if labels == v.category_labels)


def test_case_9_entity_inside_a_segment():
    v = values("cabinet", "bank", period_end=date(2025, 12, 31))
    out = render("{entity}/{fy} {entity}/Documents annuels", "{date:YYYY-MM-DD}", v)
    assert out.folder == "Cabinet Marchand/2025 Cabinet Marchand/Documents annuels"


def test_entity_inside_a_segment_never_expands_the_sub_unit():
    v = values("personal", "tax", unit="paul", doc_date=date(2026, 5, 12))
    out = render("{entity}/{entity} {year}", "{date:YYYY}", v)
    assert out.folders == ("Personnel", "Paul", "Personnel 2026")


def test_no_entity_is_not_renderable():
    with pytest.raises(NotRenderable):
        render(*TEMPLATES["tax"], values(None, "tax", doc_date=date(2026, 1, 1)))


def test_empty_segments_are_dropped_and_an_empty_path_is_not_renderable():
    v = values("cabinet", "insurance", counterparty=None, doc_date=date(2025, 1, 2))
    assert render(*TEMPLATES["insurance"], v).folders == ("Cabinet Marchand", "Assurances", "2025")
    with pytest.raises(NotRenderable):
        render("{sub}/{reference}", "{date:YYYY}", v)


def test_empty_reference_leaves_no_double_or_trailing_underscore():
    v = values("cabinet", "insurance", counterparty="UNIM", doc_date=date(2025, 1, 2))
    out = render(*TEMPLATES["insurance"], v)
    assert out.file_name == "2025-01-02_UNIM.pdf"
    assert "__" not in out.file_name


def test_file_names_drop_diacritics_and_folders_keep_them():
    v = values(
        "cabinet", "insurance", counterparty="Société Générale ș ț é ç", doc_date=date(2025, 1, 2)
    )
    out = render(*TEMPLATES["insurance"], v)
    assert out.file_name == "2025-01-02_Societe-Generale-s-t-e-c.pdf"
    assert out.folders[2] == "Société Générale ș ț é ç"


def test_slug_and_literal_rules():
    assert slug("  N° 77/12 ") == "N-77-12"
    assert slug("...a.b..") == "a.b"
    v = values("cabinet", "tax", counterparty="X", doc_date=date(2025, 1, 2))
    out = render("{entity}", "{date:YYYY}_Déclaration {counterparty}", v)
    assert out.file_name == "2025_D-claration-X.pdf"


def test_separator_runs_fold():
    assert file_stem("a_-_b--c__d-") == "a_b-c_d"
    assert file_stem("-_a") == "a"


def test_stem_cap_cuts_at_a_separator_keeping_room_for_the_suffix():
    long_ref = "-".join(["ABCDEFGHIJ"] * 15)
    v = values(
        "cabinet", "insurance", counterparty="UNIM", reference=long_ref, doc_date=date(2025, 1, 2)
    )
    out = render(*TEMPLATES["insurance"], v)
    stem = out.file_name.removesuffix(".pdf")
    assert len(stem) <= 116 and stem.endswith("ABCDEFGHIJ")
    assert stem == "2025-01-02_UNIM_" + "-".join(["ABCDEFGHIJ"] * 9)


def test_stem_cap_without_a_late_separator_cuts_at_116():
    assert file_stem("2025_" + "x" * 200) == "2025_" + "x" * 111
    assert len(file_stem("y" * 300)) == 116


def test_folder_segment_of_four_byte_characters_fits_name_max():
    seg = folder_segment("\U0001f4c4" * 80)
    assert len(seg.encode("utf-8")) <= 255
    assert seg == "\U0001f4c4" * 63
    assert folder_segment("a" * 100) == "a" * 80


def test_folder_segment_sanitises():
    assert folder_segment(' a\\b:c*d?e"f<g>h|i\x01j\x7f  k. ') == "a-b-c-d-e-f-g-h-i-j- k"
    assert folder_segment("...") == ""


def test_rendering_is_deterministic():
    v = CASES[0][1]
    assert render(*TEMPLATES["insurance"], v) == render(*TEMPLATES["insurance"], v)


@pytest.mark.parametrize(
    ("d", "end", "fy"),
    [
        (date(2025, 12, 31), (12, 31), 2025),
        (date(2026, 1, 1), (12, 31), 2026),
        (date(2025, 9, 30), (9, 30), 2025),
        (date(2025, 10, 1), (9, 30), 2026),
        (date(2026, 3, 31), (9, 30), 2026),
        (date(2025, 2, 28), (2, 28), 2025),
        (date(2025, 3, 1), (2, 28), 2026),
        (date(2024, 2, 29), (2, 28), 2025),
    ],
)
def test_fiscal_year(d, end, fy):
    assert fiscal_year(d, *end) == fy


def test_fy_token_uses_period_end_before_doc_date():
    v = values(
        "studio", "annual_accounts", period_end=date(2025, 9, 30), doc_date=date(2025, 10, 5)
    )
    out = render(*TEMPLATES["annual_accounts"], v)
    assert out.folders[-1] == "2025" and out.penalty == 0


@pytest.mark.parametrize(
    ("kw", "token_value", "fallbacks"),
    [
        ({"doc_date": date(2025, 10, 5)}, "2026", {"fy": 10}),
        ({}, "2027", {"fy": 20, "date": 20}),
    ],
)
def test_fy_fallbacks(kw, token_value, fallbacks):
    v = values("studio", "annual_accounts", arrived_at=datetime(2026, 11, 2, tzinfo=UTC), **kw)
    out = render(*TEMPLATES["annual_accounts"], v)
    assert out.folders[-1] == token_value and dict(out.fallbacks) == fallbacks


@pytest.mark.parametrize(
    ("kw", "year", "fallbacks"),
    [
        ({"doc_date": date(2025, 3, 1), "period_end": date(2024, 12, 31)}, "2025", {}),
        ({"period_end": date(2024, 12, 31)}, "2024", {"year": 10, "date": 20}),
        ({}, "2026", {"year": 20, "date": 20}),
    ],
)
def test_year_and_date_fallbacks(kw, year, fallbacks):
    v = values("cabinet", "tax", counterparty="X", **kw)
    out = render(*TEMPLATES["tax"], v)
    assert out.folders[-1] == year and dict(out.fallbacks) == fallbacks


def test_arrival_date_is_taken_in_paris():
    late = datetime(2025, 12, 31, 23, 30, tzinfo=UTC)
    v = values("cabinet", "tax", counterparty="X", arrived_at=late)
    out = render(*TEMPLATES["tax"], v)
    assert out.folders[-1] == "2026" and out.file_name.startswith("2026-01-01_")


def test_issuer_falls_back_to_the_counterparty():
    v = values(
        "personal",
        "tax",
        subcategory="preparation",
        counterparty="OXYLEO",
        issuer="SIE de Laval",
        doc_date=date(2026, 5, 12),
    )
    assert render(*TEMPLATES["tax"], v).file_name.startswith("2026-05-12_SIE-de-Laval_")


def test_extension_follows_the_mime_type():
    v = values(
        "cabinet", "tax", counterparty="X", doc_date=date(2025, 1, 2), mime_type="image/jpeg"
    )
    assert render(*TEMPLATES["tax"], v).file_name == "2025-01-02_X.jpg"


def test_entity_filing_language_overrides_settings():
    ro = EntityInfo("ro", "Firma", filing_language="ro")
    v = RenderValues(
        entity=ro,
        arrived_at=date(2026, 1, 1),
        language="fr",
        category_labels={"en": "Bank", "fr": "Banque", "ro": "Bancă"},
    )
    assert render("{entity}/{category}", "{date:YY}", v).folders == ("Firma", "Bancă")


def test_document_fiscal_year_chain():
    studio = EntityInfo("studio", "Studio", 9, 30)
    arrived = datetime(2026, 10, 14, tzinfo=UTC)
    assert document_fiscal_year(studio, date(2025, 9, 30), date(2026, 1, 1), arrived) == 2025
    assert document_fiscal_year(studio, None, date(2025, 10, 1), arrived) == 2026
    assert document_fiscal_year(studio, None, None, arrived) == 2027
    assert document_fiscal_year(None, date(2025, 9, 30), None, arrived) is None

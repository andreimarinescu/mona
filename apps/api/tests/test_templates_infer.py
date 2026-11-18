from dataclasses import replace
from datetime import UTC, date, datetime

import pytest

from mona.templates import render
from mona.templates.infer import InferError, infer, normalise
from tests.c5_registry import values


def statement(d: date = date(2026, 1, 16), **kw):
    return values(
        "lmnp", "bank", unit="angers-strasbourg", subcategory="releve",
        counterparty=kw.pop("counterparty", "Hello bank"), doc_date=d, **kw,
    )  # fmt: skip


@pytest.mark.parametrize(
    ("example", "pattern"),
    [
        ("2026-01-HB-LMNP-Janvier.pdf", "{date:YYYY-MM}-HB-{entity}-{date:MMMM}"),
        ("2026-01-16 Hello bank  Relevé de compte", "{date:YYYY-MM-DD}-{counterparty}-{sub}"),
        ("2026-01-16_Hello-bank_Releve-de-compte.PDF", "{date:YYYY-MM-DD}_{counterparty}_{sub}"),
        ("2026-01-_HB", "{date:YYYY-MM}_HB"),
        ("2026-01-", "{date:YYYY-MM}"),
        ("2026.01.16 Hello bank", "{date:YYYY.MM.DD}-{counterparty}"),
        ("16-01-2026_Hello bank", "{date:DD-MM-YYYY}_{counterparty}"),
        ("20260116_LMNP", "{date:YYYYMMDD}_{entity}"),
        ("2026-01_Releve_2026", "{date:YYYY-MM}_Releve_{date:YYYY}"),
        ("2026-01_Janvier-Hello-bank", "{date:YYYY-MM}_{date:MMMM}-{counterparty}"),
        ("2026-01_HB-Hello-banks", "{date:YYYY-MM}_HB-Hello-banks"),
    ],
)
def test_infers_the_pattern_and_it_round_trips(example, pattern):
    v = statement()
    out = infer(example, v)
    assert out.pattern == pattern
    assert render("x", out.pattern, v).file_name == f"{out.stem}.pdf"
    assert out.stem == normalise(example)


def test_accents_and_spaces_are_normalised_first():
    assert normalise("  2026-01 Relevé   Médical ș.pdf ") == "2026-01-Releve-Medical-s"
    assert infer("2026-01 Relevé Médical", statement()).pattern == "{date:YYYY-MM}-Releve-Medical"


def test_a_literal_10_and_a_two_character_reference_stay_literals():
    v = statement(date(2026, 10, 5), reference="R1")
    assert infer("2026-10-05_HB_10_R1", v).pattern == "{date:YYYY-MM-DD}_HB_10_R1"
    v = statement(date(2026, 10, 5), reference="2025-A-118")
    assert infer("2026-10_2025-A-118", v).pattern == "{date:YYYY-MM}_{reference}"


def test_marchand_is_no_month():
    v = statement(date(2026, 3, 5))
    assert infer("2026-03-Marchand", v).pattern == "{date:YYYY-MM}-Marchand"


def test_mmmm_is_inferred_only_in_the_filing_language():
    ro = replace(statement(), language="ro")
    assert infer("2026-01-HB-Ianuarie", ro).pattern == "{date:YYYY-MM}-HB-{date:MMMM}"
    with pytest.raises(InferError) as e:
        infer("2026-01-HB-Ianuarie", statement())
    assert e.value.hint == "{date:MMMM}"


@pytest.mark.parametrize("example", ["2026-01-HB-January", "2026-01_mars", "2026-01-HB-Mai"])
def test_a_month_name_in_a_literal_is_refused_naming_the_token(example):
    with pytest.raises(InferError) as e:
        infer(example, statement())
    assert e.value.hint == "{date:MMMM}" and "{date:MMMM}" in e.value.message


@pytest.mark.parametrize(
    "example", ["Hello bank 2026-01", "2025-01-16_HB", "16-02_HB", "01-16_HB", "16_HB", ""]
)
def test_the_name_must_start_with_the_document_date(example):
    with pytest.raises(InferError) as e:
        infer(example, statement())
    assert "2026-01-16" in e.value.message


def test_the_date_is_the_arrival_date_without_a_doc_date():
    v = statement(None, arrived_at=datetime(2026, 4, 2, 9, tzinfo=UTC))
    assert infer("2026-04_HB", v).pattern == "{date:YYYY-MM}_HB"


def test_ties_go_counterparty_before_entity_and_longest_match_wins():
    v = statement(counterparty="LMNP", reference="LMNP-Angers")
    assert infer("2026-01_LMNP", v).pattern == "{date:YYYY-MM}_{counterparty}"
    assert infer("2026-01_LMNP-Angers", v).pattern == "{date:YYYY-MM}_{reference}"


def test_leading_date_prefers_year_month_day_then_day_month_year():
    v = statement(date(2026, 1, 1))
    assert infer("2026-01-01_x", v).pattern == "{date:YYYY-MM-DD}_x"
    assert infer("01-01-2026_x", v).pattern == "{date:DD-MM-YYYY}_x"


def test_a_name_that_does_not_round_trip_is_refused_with_the_name_it_would_give():
    long = "2026-01-" + "-".join(["Releve"] * 25)
    with pytest.raises(InferError) as e:
        infer(long, statement())
    assert e.value.hint is not None and len(e.value.hint) <= 116
    assert long.startswith(e.value.hint)

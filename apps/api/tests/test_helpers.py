import re

import pytest

from mona.iban import iban_candidates, iban_hash, iban_last4, is_valid_iban, normalize_iban
from mona.ids import PREFIXES, is_id, new_id
from mona.naming import to_camel, to_snake
from mona.text import contains_word, norm

# Synthetic IBANs with valid check digits (not real accounts).
FR_IBAN = "FR7630006000011234567890189"
RO_IBAN = "RO49AAAA1B31007593840000"
DE_IBAN = "DE89370400440532013000"


def test_new_id_shape_and_prefix():
    value = new_id("doc")
    assert re.fullmatch(r"doc_[0-9a-hjkmnp-tv-z]{26}", value)
    assert is_id(value) and is_id(value, "doc") and not is_id(value, "ent")


@pytest.mark.parametrize(
    "value",
    [
        "doc_01J9ZQ3K8E6Y4V2M7C5R1T0B9A",  # upper case
        "doc_01j9zq3k8e6y4v2m7c5r1t0b9",  # 25 chars
        "doc_01j9zq3k8e6y4v2m7c5r1t0bia",  # i is not Crockford
        "doc-01j9zq3k8e6y4v2m7c5r1t0b9a",
        None,
    ],
)
def test_is_id_rejects(value):
    assert not is_id(value)


def test_new_ids_sort_by_creation_time():
    import time

    first = new_id("rul")
    time.sleep(0.002)
    assert new_id("rul") > first


def test_ids_generated_in_one_burst_are_strictly_increasing():
    ids = [new_id("not") for _ in range(5000)]
    assert ids == sorted(set(ids))


def test_prefixes_cover_c1_table():
    assert len(PREFIXES) == 26
    assert len(set(PREFIXES.values())) == 26
    assert PREFIXES["auth_sessions"] == "ses"
    assert PREFIXES["card_action_notes"] == "not" and PREFIXES["card_events"] == "crd"


# C5 §2 steps and C5 §11 test 1 vectors.
NORM_VECTORS = [
    ("a\u00a0b", "a b"),
    ("1\u202f284,00 \u20ac", "1 284,00 \u20ac"),
    ("contri\u00adbution", "contribution"),
    ("l\u2019avis", "l'avis"),
    ("\u2018x\u2019 \u201ax\u201b \u02bcx\u0060 x\u2032", "'x' 'x' 'x' x'"),
    ("\u201cx\u201d \u201ex\u201f \u00abx\u00bb \u2039x\u203a", '"x" "x" "x" "x"'),
    ("a\u2010b\u2011c\u2012d\u2013e\u2014f\u2015g\u2212h", "a-b-c-d-e-f-g-h"),
    ("etc\u2026", "etc..."),
    ("\ufb01chier", "fichier"),
    ("\u0219\u015f\u021b\u0163", "sstt"),
    ("\u0218\u015e\u021a\u0162", "sstt"),
    ("Societatea \u0218tiin\u021bific\u0103", "societatea stiintifica"),
    ("\u015ftiin\u0163ific\u0103", "stiintifica"),
    ("\u00c9ch\u00e9ance", "echeance"),
    ("E\u0301cole", "ecole"),
    ("  Relev\u00e9\tde\n\ncompte \r\n ", "releve de compte"),
    ("Stra\u00dfe", "strasse"),
    ("", ""),
]


@pytest.mark.parametrize(("raw", "expected"), NORM_VECTORS)
def test_norm(raw, expected):
    assert norm(raw) == expected


def test_norm_is_idempotent():
    for raw, _ in NORM_VECTORS:
        assert norm(norm(raw)) == norm(raw)


def test_contains_word_is_whole_word():
    assert contains_word(norm("Appel OPCO 2025"), norm("OPCO"))
    assert not contains_word(norm("OPCOMMERCE"), norm("OPCO"))
    assert contains_word(norm("plan d’épargne retraite"), norm("plan d'épargne"))
    assert not contains_word("ab1", "ab")


@pytest.mark.parametrize("iban", [FR_IBAN, RO_IBAN, DE_IBAN, "fr76 3000 6000 0112 3456 7890 189"])
def test_valid_ibans(iban):
    assert is_valid_iban(iban)


@pytest.mark.parametrize(
    "iban",
    [
        "FR7630006000011234567890188",  # bad checksum
        "FR76300060000112345678901",  # FR must be 27
        "RO49AAAA1B310075938400001",  # RO must be 24
        "DE8937040044",  # too short
        "not an iban",
    ],
)
def test_invalid_ibans(iban):
    assert not is_valid_iban(iban)


def test_iban_hash_and_last4():
    key = bytes(range(32))
    grouped = "FR76 3000 6000 0112 3456 7890 189"
    assert normalize_iban(grouped) == FR_IBAN
    assert iban_hash(grouped, key) == iban_hash(FR_IBAN.lower(), key)
    assert re.fullmatch(r"[0-9a-f]{64}", iban_hash(FR_IBAN, key))
    assert iban_hash(FR_IBAN, key) != iban_hash(FR_IBAN, bytes(32))
    assert FR_IBAN not in iban_hash(FR_IBAN, key)
    assert iban_last4(grouped) == "0189"


def test_iban_candidates():
    bad = "FR7630006000011234567890188"
    text = f"IBAN : fr76 3000 6000 0112 3456 7890 189\nautre {DE_IBAN} faux {bad}"
    assert iban_candidates(text) == [FR_IBAN, DE_IBAN]


@pytest.mark.parametrize(
    ("snake", "camel"),
    [
        ("sub_unit_id", "subUnitId"),
        ("fiscal_year", "fiscalYear"),
        ("id", "id"),
        ("iban_last4", "ibanLast4"),
        ("moves_total", "movesTotal"),
    ],
)
def test_naming_round_trip(snake, camel):
    assert to_camel(snake) == camel
    assert to_snake(camel) == snake

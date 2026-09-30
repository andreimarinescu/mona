# /// script
# requires-python = ">=3.12"
# dependencies = ["pytest"]
# ///
import sys

import pytest
from _evidence import norm, verify

PAGES = ["FACTURE N° 42\nDate : 14/04/2025\nMontant TTC :   1 240,50 €",
         "Société Exemple SARL\nL’échéance est fixée au 30/04/2025"]


def f(quote, page):
    return {"value": "x", "quote": quote, "page": page}


def test_norm_folds_case_diacritics_and_narrow_spaces():
    assert norm("  Société EXEMPLE \n SARL ") == "societe exemple sarl"
    assert norm("1\u202f240,50\u00a0\u20ac") == "1 240,50 \u20ac"


@pytest.mark.parametrize("field,expected", [
    (f("Montant TTC : 1 240,50 €", 1), "ok"),
    (f("societe exemple sarl", 2), "ok"),
    (f("Date : 14/04/2025", 2), "wrong_page"),
    (f("L'echeance est fixee au 30/04/2025", 2), "punctuation"),
    (f("FACTURE N°42", 1), "ocr_spacing"),
    (f("Date : 14/04/2026", 1), "near_miss"),
    (f("Invoice dated April 14th", 1), "paraphrase"),
    (f("", 1), "empty_quote"),
    (f("Date : 14/04/2025", 7), "wrong_page"),
    (None, "null"),
])
def test_verify(field, expected):
    assert verify(field, PAGES) == expected


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))

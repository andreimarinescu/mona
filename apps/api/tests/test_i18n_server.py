"""The server catalog (C8 §1.1), its formatter and `detect_language` (C8 §11 items 2, 3 and 7)."""

import re

import pytest

from mona.i18n import LANGS, catalog, detect_language, plural_category, t

SENTENCES = ("default", "low", "entity", "conflict", "asked", "unreadable")
CONTRACT_KEYS = [f"review.sentence.{k}{v}" for k in SENTENCES for v in ("", "_anon")] + [
    "review.sentence.first",
    "interview.option.ask",
]
PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def flatten(node: dict, prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in node.items():
        key = f"{prefix}.{k}" if prefix else k
        out.update(flatten(v, key) if isinstance(v, dict) else {key: v})
    return out


def test_every_language_has_the_same_keys_and_placeholders():
    flat = {lang: flatten(catalog(lang)) for lang in LANGS}
    assert set(flat["fr"]) == set(flat["en"]) == set(flat["ro"])
    for key, text in flat["en"].items():
        wanted = set(PLACEHOLDER.findall(text))
        for lang in ("fr", "ro"):
            assert set(PLACEHOLDER.findall(flat[lang][key])) == wanted, (lang, key)
            assert flat[lang][key].strip(), (lang, key)


@pytest.mark.parametrize("lang", LANGS)
def test_the_contract_keys_exist(lang):
    flat = flatten(catalog(lang))
    assert [k for k in CONTRACT_KEYS if k not in flat] == []


def test_romanian_uses_comma_below():
    assert not re.search("[ŞşŢţ]", str(catalog("ro")))


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("reason", SENTENCES)
@pytest.mark.parametrize(("counterparty", "doc_type"), [("UNIM", "avis"), (None, None)])
def test_review_sentences_render_cleanly(lang, reason, counterparty, doc_type):
    text = t(
        f"review.sentence.{reason}", lang, context=None if counterparty else "anon",
        counterparty=counterparty or "", docType=f" ({doc_type})" if doc_type else "",
        entity="Cabinet Marchand", category="Assurances",
    )  # fmt: skip
    assert "{{" not in text and " ()" not in text and "belongs to ," not in text
    if counterparty and reason not in ("asked", "unreadable"):
        assert "UNIM (avis)" in text


@pytest.mark.parametrize(
    ("lang", "text"),
    [("en", "Ask me each time"), ("fr", "Me demander à chaque fois"),
     ("ro", "Întrebați-mă de fiecare dată")],
)  # fmt: skip
def test_the_ask_option(lang, text):
    assert t("interview.option.ask", lang) == text


def test_romanian_plural_categories():
    assert [plural_category(n, "ro") for n in (1, 2, 5, 20, 101)] == [
        "one", "few", "few", "other", "few",
    ]  # fmt: skip
    assert [plural_category(n, "fr") for n in (0, 1, 2, 1_000_000)] == [
        "one", "one", "other", "many",
    ]  # fmt: skip


def test_an_unknown_language_falls_back_to_english():
    assert t("interview.option.ask", "de") == "Ask me each time"


C8_VECTORS = [
    ("How much did we pay AGIPI last year?", "en"),
    ("What's due this month?", "en"),
    ("Let's go through your questions about this batch.", "en"),
    ("Rédigez une réponse au SIE pour demander un échéancier", "fr"),
    ("Combien avons-nous payé à AGIPI l'année dernière ?", "fr"),
    ("Passons en revue les questions sur ce lot.", "fr"),
    ("Cât am plătit la AGIPI anul trecut?", "ro"),
    ("Cat am platit la AGIPI anul trecut?", "ro"),
    ("Ce avem de plătit luna asta?", "ro"),
    ("Ce facturi avem de la AGIPI?", "ro"),
    ("Să trecem prin întrebările despre acest lot.", "ro"),
    ("Bună ziua", "ro"),
    ("Merci", None),
    ("OK", None),
    ("AGIPI 2025", None),
    ("URSSAF Q3 invoice", None),
    ("Open the Prévoyance folder", "en"),
    ("What's in Impôts et taxes?", "en"),
    ("Show me the Relevé de compte from Hello bank", "en"),
    ("open the prévoyance folder", "en"),
]
C3_SENTENCES = [
    ("Combien avons-nous payé à l'URSSAF ?", "fr"),
    ("Câte documente AGIPI avem în arhivă?", "ro"),
    ("Cat am platit pentru asigurari si ce este scadent?", "ro"),
    ("Buna\u0306 ziua", "ro"),
]


@pytest.mark.parametrize(("text", "lang"), C8_VECTORS + C3_SENTENCES)
def test_detect_language(text, lang):
    assert detect_language(text) == lang

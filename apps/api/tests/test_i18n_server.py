"""The server catalog (C8 §1.1) and its formatter (C8 §11 items 3 and 7)."""

import re

import pytest

from mona.i18n import LANGS, catalog, plural_category, t

SENTENCES = ("default", "low", "entity", "conflict", "asked", "unreadable")
CONTRACT_KEYS = [f"review.sentence.{k}{v}" for k in SENTENCES for v in ("", "_anon")] + [
    "interview.option.ask"
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

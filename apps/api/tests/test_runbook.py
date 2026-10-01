"""L6: the runbooks fit one page each, agree with each other, and use real commands."""

import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
DOCS = {"en": ROOT / "docs" / "runbook.md", "fr": ROOT / "docs" / "runbook.fr.md"}
WRAPPER = (ROOT / "deploy" / "bin" / "mona").read_text()
ONE_PAGE_WORDS = 500


def commands(text: str) -> set[str]:
    return {m.strip() for m in re.findall(r"`(mona [^`]+)`", text)}


@pytest.mark.parametrize("lang", DOCS)
def test_each_runbook_fits_one_page(lang):
    assert len(DOCS[lang].read_text().split()) <= ONE_PAGE_WORDS


def test_both_languages_give_the_same_commands():
    assert commands(DOCS["en"].read_text()) == commands(DOCS["fr"].read_text())


@pytest.mark.parametrize("lang", DOCS)
def test_every_command_is_one_the_wrapper_handles(lang):
    wrapper_cases = set(re.findall(r"^\s+([a-z][a-z-]*(?:\|[a-z-]+)*)\)", WRAPPER, re.M))
    for command in commands(DOCS[lang].read_text()):
        assert command.split()[1] in wrapper_cases, command


@pytest.mark.parametrize("lang", DOCS)
def test_the_stage_privacy_line_and_the_origin_are_there(lang):
    text = DOCS[lang].read_text()
    assert "MONA_PUBLIC_ORIGIN" in text and "24" in text and "doctor" in text


@pytest.mark.parametrize("lang", DOCS)
def test_no_practice_names(lang):
    spec = importlib.util.spec_from_file_location(
        "guard", ROOT / "scripts" / "no-practice-names.py"
    )
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    text = DOCS[lang].read_text().casefold()
    for name in set(guard.names(ROOT / "demo" / "seed" / "practice.yaml")) - {"Claudiu"}:
        assert not re.search(rf"\b{re.escape(name.casefold())}\b", text), name

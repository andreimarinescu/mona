"""C9 §8 test 4: the Telegram first-line checker (§3.5)."""

from pathlib import Path

import pytest

from mona.firstline import first_line, first_line_problems, registry_names

VOICE = Path(__file__).resolve().parents[3] / "design" / "mona-design-system" / "voice-and-tone.md"


@pytest.fixture
def names(seeded_engine) -> list[str]:
    with seeded_engine.connect() as conn:
        return registry_names(conn)


def voice_row(label: str) -> list[str]:
    """The EN, FR and RO cells of a voice-and-tone example row."""
    for line in VOICE.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip("|").split("|")]
        if cells[0] == label:
            return cells[1:4]
    raise AssertionError(label)


@pytest.mark.parametrize(
    ("line", "problem"),
    [
        ("Studio NUMÉRIQUE has two documents for you.", "name"),
        ("Two letters from opco need your review.", "name"),
        ("HELLO BANK! sent a statement.", "name"),
        ("A.G.I.P.I. wrote again.", "name"),
        ("Paul has a document waiting.", "name"),
        ("Le dossier personnel attend votre avis.", "name"),
        ("€1,284.60 is waiting for you.", "amount"),
        ("Un paiement de 1 284,60 € attend.", "amount"),
        ("4.812,00 lei de plată.", "amount"),
        ("120 EUR to pay this week.", "amount"),
        ("One payment of 99.90 needs your eye.", "amount"),
        ("Something is due 14/03/2026.", "date"),
        ("Something is due 2026-03-14.", "date"),
        ("Something is due on 14 March.", "date"),
        ("Something is due Oct 14.", "date"),
        ("Une échéance le 1er octobre.", "date"),
        ("Ceva este scadent pe 14 octombrie.", "date"),
        ("Un document de martie 2026.", "date"),
        ("Pay to FR76 3000 6000 0112 3456 7890 189 today.", "iban"),
    ],
)
def test_crafted_first_lines_are_flagged(names, line, problem):
    assert problem in first_line_problems(line, names)


@pytest.mark.parametrize(
    "line",
    [
        *voice_row("Telegram, locked-screen line"),
        "3 documents need your review.",
        "You have 1 reminder today and 2 documents to review.",
        "Sept documents attendent votre avis.",
        "Mai sunt 2 documente de verificat.",
        "Nothing needs your attention today.",
    ],
)
def test_count_only_first_lines_pass(names, line):
    assert first_line_problems(line, names) == []


def test_reminder_templates_would_break_the_first_line(names):
    for line in voice_row("Reminder"):
        assert {"amount", "date"} <= set(first_line_problems(line, names)), line


def test_only_the_first_line_counts(names):
    details = "Two documents need your review.\nOPCO EP: €1,284.60, due 14 Oct."
    late = "x" * 100 + " OPCO EP €1,284.60"
    early = "x" * 80 + " OPCO EP"
    assert first_line(details) == "Two documents need your review."
    assert first_line_problems(details, names) == []
    assert first_line_problems(late, names) == []
    assert first_line_problems(early, names) == ["name"]

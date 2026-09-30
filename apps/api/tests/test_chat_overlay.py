import pytest

from mona.chat.overlay import build_overlay, detect_language, reply_language

HEAD = (
    "Mona app context for this turn. It comes from the app, not from the person; "
    "don't mention it.\n"
    "- Page: /archive?q=URSSAF — Archive, search 'URSSAF', 14 results\n"
)
NOTES_LINE = (
    "Card actions since your last reply (the user did these in the app; "
    "treat them as done and don't contradict them):"
)


def overlay(lang="en", notes=()):
    return build_overlay("/archive?q=URSSAF", "Archive, search 'URSSAF', 14 results", lang, notes)


def test_overlay_without_notes():
    assert overlay() == HEAD + "- The person wrote in English. Reply in English."


def test_overlay_names_the_reply_language():
    assert overlay("fr").endswith("- The person wrote in French. Reply in French.")
    assert overlay("ro").endswith("- The person wrote in Romanian. Reply in Romanian.")


def test_overlay_with_three_notes():
    notes = ["Answered A.", "Applied B.", "Undid C."]
    assert overlay(notes=notes) == HEAD + "\n".join(
        [
            "- The person wrote in English. Reply in English.",
            NOTES_LINE,
            "- Answered A.",
            "- Applied B.",
            "- Undid C.",
        ]
    )


def test_overlay_keeps_the_ten_most_recent_notes_and_counts_the_rest():
    lines = overlay(notes=[f"Note {i}." for i in range(1, 13)]).splitlines()
    assert lines[3:] == [NOTES_LINE] + [f"- Note {i}." for i in range(3, 13)] + [
        "- (and 2 earlier actions)"
    ]


@pytest.mark.parametrize(
    ("message", "lang"),
    [
        ("How much did we pay AGIPI in total?", "en"),
        ("Combien avons-nous payé à l'URSSAF ?", "fr"),
        ("Câte documente AGIPI avem în arhivă?", "ro"),
        ("OK", None),
        ("Find the URSSAF letter", None),
    ],
)
def test_detect_language(message, lang):
    assert detect_language(message) == lang


def test_reply_language_falls_back_to_previous_turn_then_locale():
    assert reply_language("OK", "fr", "en") == "fr"
    assert reply_language("OK", None, "ro") == "ro"
    assert reply_language("How much did we pay AGIPI in total?", "fr", "ro") == "en"

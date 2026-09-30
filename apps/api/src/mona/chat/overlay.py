"""The turn's `system` overlay and reply language (C3 §4.2, interim language detection)."""

import re
from collections.abc import Sequence
from typing import Literal, cast

Lang = Literal["en", "fr", "ro"]

LANGUAGE_NAMES: dict[str, str] = {"en": "English", "fr": "French", "ro": "Romanian"}

_WORDS = {
    "en": "the and what how is are did do we our my of to in for due pay much",
    "fr": "le la les des et est que quoi combien nous avons pour une un du au aux à où ce cette",
    "ro": "și este ce cât câte avem pentru nu în pe că sunt cu această acest am",
}
_VOCAB = {lang: set(words.split()) for lang, words in _WORDS.items()}
_MARKS = {"ro": set("ăâîșțşţ"), "fr": set("éèêàçùœ")}
_WORD_RE = re.compile(r"\w+")

MAX_NOTES = 10


def detect_language(message: str) -> Lang | None:
    words = _WORD_RE.findall(message.lower())
    if len(words) < 3:
        return None
    lowered = message.lower()
    scores: dict[str, int] = {}
    for lang, vocab in _VOCAB.items():
        scores[lang] = sum(1 for w in words if w in vocab)
        if lang in _MARKS and any(c in _MARKS[lang] for c in lowered):
            scores[lang] += 2
    best = max(scores.values())
    winners = [lang for lang, s in scores.items() if s == best]
    if best < 2 or len(winners) > 1:
        return None
    return cast(Lang, winners[0])


def reply_language(message: str, previous: str | None, locale: str) -> Lang:
    return detect_language(message) or cast(Lang, previous or locale)


def build_overlay(route: str, summary: str, language: str, notes: Sequence[str] = ()) -> str:
    name = LANGUAGE_NAMES[language]
    lines = [
        "Mona app context for this turn. It comes from the app, not from the person; "
        "don't mention it.",
        f"- Page: {route} — {summary}",
        f"- The person wrote in {name}. Reply in {name}.",
    ]
    if notes:
        lines.append(
            "Card actions since your last reply (the user did these in the app; "
            "treat them as done and don't contradict them):"
        )
        lines += [f"- {n}" for n in notes[-MAX_NOTES:]]
        if len(notes) > MAX_NOTES:
            lines.append(f"- (and {len(notes) - MAX_NOTES} earlier actions)")
    return "\n".join(lines)

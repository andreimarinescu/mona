import re
import unicodedata

_PUNCT = str.maketrans(
    {
        "\u00ad": None,
        **dict.fromkeys("\u2018\u2019\u201a\u201b\u02bc\u0060\u2032", "'"),
        **dict.fromkeys("\u201c\u201d\u201e\u201f\u00ab\u00bb\u2039\u203a", '"'),
        **dict.fromkeys("\u2010\u2011\u2012\u2013\u2014\u2015\u2212", "-"),
        "\u2026": "...",
    }
)
_WS = re.compile(r"\s+")


def norm(s: str) -> str:
    """C5 §2 normalisation."""
    s = unicodedata.normalize("NFKC", s)
    s = s.translate(_PUNCT)
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    s = s.casefold()
    return _WS.sub(" ", s).strip()


def contains_word(haystack: str, needle: str) -> bool:
    """C5 §2 whole-word match; both sides already normalised."""
    return re.search(rf"(?<![0-9a-z]){re.escape(needle)}(?![0-9a-z])", haystack) is not None

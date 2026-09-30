"""C5 §2 norm() and whole-word matching, used by the local corpus checks (not application code)."""

import re
import unicodedata

PUNCT = {
    **dict.fromkeys("‘’‚‛ʼ`′", "'"),
    **dict.fromkeys("“”„‟«»‹›", '"'),
    **dict.fromkeys("‐‑‒–—―−", "-"),
    "…": "...",
}


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).replace("­", "")
    text = "".join(PUNCT.get(c, c) for c in text)
    text = "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", text.casefold()).strip()


def whole_word(needle: str, haystack: str) -> bool:
    return re.search(r"(?<![0-9a-z])" + re.escape(needle) + r"(?![0-9a-z])", haystack) is not None

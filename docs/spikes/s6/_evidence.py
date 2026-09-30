"""Extended evidence schema (C5 preview), page-delimited prompts and quote verification."""
import difflib
import re
import unicodedata

FIELDS = ["entity_hint", "category", "counterparty", "doc_type", "doc_date", "period_start",
          "period_end", "amount", "due_date", "addressee"]
DATE_FIELDS = {"doc_date", "period_start", "period_end", "due_date"}


def evidence_schema(categories: list[str], max_len: int | None = None,
                    evidence_first: bool = False) -> dict:
    def _field(value_schema: dict, extra: dict | None = None) -> dict:
        quote = {"type": "string", **({"maxLength": max_len} if max_len else {})}
        ev = {"page": {"type": "integer", "minimum": 1}, "quote": quote}
        val = {"value": value_schema, **(extra or {})}
        props = {**ev, **val} if evidence_first else {**val, **ev}
        return {"type": "object", "properties": props, "required": list(props),
                "additionalProperties": False}

    date = {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"}
    text = {"type": "string", **({"maxLength": max_len} if max_len else {})}
    nullable = lambda s: {"anyOf": [s, {"type": "null"}]}
    props = {
        "entity_hint": nullable(_field(text)),
        "category": _field({"type": "string", "enum": categories}),
        "counterparty": nullable(_field(text)),
        "doc_type": nullable(_field(text)),
        "doc_date": nullable(_field(date)),
        "period_start": nullable(_field(date)),
        "period_end": nullable(_field(date)),
        "amount": nullable(_field({"type": "number"}, {"currency": {"type": "string", "pattern": "^[A-Z]{3}$"}})),
        "due_date": nullable(_field(date)),
        "addressee": nullable(_field(text)),
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    }
    return {"type": "object", "properties": props, "required": list(props),
            "additionalProperties": False}


FIELD_GUIDE = """
Evidence extraction (this overrides the output format above). Return one JSON object with these fields; each field is {"value", "quote", "page"} or null when the document does not state it:
- entity_hint: the company or person the document concerns or is addressed to on the practice side
- category: one of the categories above
- counterparty: the issuer or other party (supplier, bank, insurer, administration)
- doc_type: the document's own title or kind (e.g. facture, avis d'echeance, releve de compte)
- doc_date: the document's issue date, as YYYY-MM-DD
- period_start / period_end: the period covered (statement period, fiscal year, contract term), as YYYY-MM-DD
- amount: the main amount due or paid, as a number, plus "currency" (ISO 4217, e.g. EUR)
- due_date: payment or response deadline, as YYYY-MM-DD
- addressee: the person or company the document is addressed to, as written
- confidence: 0-1 for the category
"""

QUOTE_RULES = {
    "p0": """
"quote" is a verbatim excerpt of the document text that supports the value; "page" is the page it appears on.""",
    "p1": """
Rules for "quote":
- Copy a short span (3 to 12 words) character for character from ONE line of the document text: same spelling, accents, capitals, punctuation and odd spacing, even if the OCR looks wrong.
- Never translate, reformat, abbreviate or join text from different lines. Dates and amounts are quoted as printed, even though "value" is normalised.
- "page" is the number in the nearest page marker above the quoted line.
- If you cannot find a supporting span, return null for the field.""",
}


def page_block(pages: list[str], style: str) -> str:
    if style == "xml":
        return "\n".join(f'<page number="{i}">\n{t.strip()}\n</page>' for i, t in enumerate(pages, 1))
    return "\n".join(f"=== PAGE {i} ===\n{t.strip()}" for i, t in enumerate(pages, 1))


_WS = re.compile(r"\s+")
_PUNCT = str.maketrans({"\u2019": "'", "\u2018": "'", "\u02bc": "'", "`": "'", "\u201c": '"',
                        "\u201d": '"', "\u00ab": '"', "\u00bb": '"', "\u2013": "-", "\u2014": "-",
                        "\u2010": "-", "\u2011": "-", "\u2026": "..."})


def norm(s: str) -> str:
    s = s.replace("\u00a0", " ").replace("\u202f", " ")
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    return _WS.sub(" ", s.lower()).strip()


def norm_punct(s: str) -> str:
    return norm(s).translate(_PUNCT)


def _nows(s: str) -> str:
    return norm_punct(s).replace(" ", "")


def best_ratio(quote: str, page: str) -> float:
    q, p = norm_punct(quote), norm_punct(page)
    if not q or not p:
        return 0.0
    starts = {max(0, b.a - b.b + d)
              for b in difflib.SequenceMatcher(None, p, q, autojunk=False).get_matching_blocks()[:-1]
              for d in (-2, -1, 0, 1, 2)}
    return max((difflib.SequenceMatcher(None, p[s:s + len(q)], q, autojunk=False).ratio()
                for s in starts), default=0.0)


def verify(field: dict | None, pages: list[str]) -> str:
    """Return 'ok' or the failure cause for one {value, quote, page} field."""
    if field is None:
        return "null"
    quote, page = (field.get("quote") or "").strip(), field.get("page")
    if not quote:
        return "empty_quote"
    idx = page - 1 if isinstance(page, int) and 1 <= page <= len(pages) else None
    if idx is not None and norm(quote) in norm(pages[idx]):
        return "ok"
    if any(norm(quote) in norm(p) for p in pages):
        return "wrong_page"
    if idx is not None and norm_punct(quote) in norm_punct(pages[idx]):
        return "punctuation"
    if any(_nows(quote) in _nows(p) for p in pages):
        return "ocr_spacing"
    if max(best_ratio(quote, p) for p in pages) >= 0.85:
        return "near_miss"
    return "paraphrase"

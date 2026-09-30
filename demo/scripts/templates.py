"""Draft path and file-name template renderer for the demo seed (validates tokens; not application code)."""

import re
import unicodedata
from datetime import date
from pathlib import Path

import yaml

SEED_DIR = Path(__file__).resolve().parents[1] / "seed"
TOKENS = {"entity", "year", "fy", "category", "sub", "counterparty", "issuer", "reference", "date"}
TOKEN_RE = re.compile(r"\{(\w+)(?::([^}]*))?\}")


def load_practice() -> dict:
    return yaml.safe_load((SEED_DIR / "practice.yaml").read_text(encoding="utf-8"))


def load_rules() -> dict:
    return yaml.safe_load((SEED_DIR / "rules.yaml").read_text(encoding="utf-8"))


def template_tokens(template: str) -> set[str]:
    return {m.group(1) for m in TOKEN_RE.finditer(template)}


def fiscal_year(period_end: date, fy_end: str | None) -> int:
    if not fy_end:
        return period_end.year
    month, day = (int(p) for p in fy_end.split("-"))
    return period_end.year if (period_end.month, period_end.day) <= (month, day) else period_end.year + 1


def _format_date(d: date, fmt: str) -> str:
    return fmt.replace("YYYY", f"{d.year:04d}").replace("MM", f"{d.month:02d}").replace("DD", f"{d.day:02d}")


def _values(practice: dict, meta: dict, doc_date: date, period_end: date | None) -> dict:
    entity = next(e for e in practice["entities"] if e["id"] == meta["entity"])
    category = next(c for c in practice["categories"] if c["id"] == meta["category"])
    entity_folder = entity["folder_name"]
    if meta.get("sub_unit"):
        unit = next(u for u in entity["sub_units"] if u["id"] == meta["sub_unit"])
        entity_folder += "/" + unit.get("label", unit["id"].capitalize())
    return {
        "entity": entity_folder,
        "year": str(doc_date.year),
        "fy": str(fiscal_year(period_end or doc_date, entity.get("fiscal_year_end"))),
        "category": category["labels"][practice["practice"]["filing_language"]],
        "sub": meta.get("subcategory", ""),
        "counterparty": meta.get("counterparty", ""),
        "issuer": meta.get("issuer", ""),
        "reference": meta.get("reference", ""),
    }


def _render(template: str, values: dict, doc_date: date) -> str:
    def sub(m: re.Match) -> str:
        name, fmt = m.group(1), m.group(2)
        if name not in TOKENS:
            raise ValueError(f"unknown template token {{{name}}}")
        if name == "date":
            return _format_date(doc_date, fmt or "YYYY-MM-DD")
        return values[name]

    return TOKEN_RE.sub(sub, template)


def render_path(practice: dict, meta: dict, doc_date: date, period_end: date | None = None) -> str:
    category = next(c for c in practice["categories"] if c["id"] == meta["category"])
    values = _values(practice, meta, doc_date, period_end)
    segments = [_render(seg, values, doc_date).strip() for seg in category["path_template"].split("/")]
    return "/".join(s for s in segments if s)


def slug(text: str) -> str:
    plain = "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")
    plain = re.sub(r"\s+", "-", plain.strip())
    return re.sub(r"[^A-Za-z0-9._-]", "", plain)


def render_file_name(practice: dict, meta: dict, doc_date: date, ext: str = "pdf") -> str:
    category = next(c for c in practice["categories"] if c["id"] == meta["category"])
    values = _values(practice, meta, doc_date, None)
    parts = [slug(_render(p, values, doc_date)) for p in category["file_template"].split("_")]
    return "_".join(p for p in parts if p) + f".{ext}"

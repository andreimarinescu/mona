"""Independent C5 §8 renderer: a cross-check for L1's implementation (not application code)."""

import os
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

SEED_DIR = Path(__file__).resolve().parents[1] / "seed"
OVERLAY_DEFAULT = Path.home() / "DevFiles" / "mona-hq" / "demo-data" / "seed" / "identifiers.yaml"
TOKEN_NAMES = {"entity", "year", "fy", "category", "sub", "counterparty", "issuer", "reference", "date"}
DATE_UNITS = ("YYYY", "YY", "MM", "DD")
DATE_SEPARATORS = "-_."
FORBIDDEN = set('\\/:*?"<>|')
MIME_EXT = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png"}
STEM_MAX = 116
STEM_CUT_MIN = 40


class TemplateError(ValueError):
    def __init__(self, message: str, offset: int):
        super().__init__(f"{message} at offset {offset}")
        self.offset = offset


class NotRenderable(ValueError):
    pass


def parse(template: str, kind: str) -> list[tuple]:
    """Parse into ("lit", text) and ("tok", name, fmt) parts; kind is "path" or "file"."""
    parts: list[tuple] = []
    i, n = 0, len(template)
    lit: list[str] = []
    while i < n:
        c = template[i]
        if c == "}":
            raise TemplateError("stray '}'", i)
        if c != "{":
            lit.append(c)
            i += 1
            continue
        if lit:
            parts.append(("lit", "".join(lit)))
            lit = []
        end = template.find("}", i + 1)
        if end < 0 or "{" in template[i + 1 : end]:
            raise TemplateError("stray '{'", i)
        body = template[i + 1 : end]
        name, sep, fmt = body.partition(":")
        if name not in TOKEN_NAMES:
            raise TemplateError(f"unknown token {name!r}", i + 1)
        if sep and name != "date":
            raise TemplateError(f"format on non-date token {name!r}", i + 1 + len(name))
        if sep:
            _check_format(fmt, i + 2 + len(name))
        parts.append(("tok", name, fmt if sep else None))
        i = end + 1
    if lit:
        parts.append(("lit", "".join(lit)))
    if kind == "path":
        _check_path(template)
    else:
        _check_file(template, parts)
    return parts


def _check_format(fmt: str, offset: int) -> None:
    if not fmt:
        raise TemplateError("empty date format", offset)
    i = 0
    while i < len(fmt):
        unit = next((u for u in DATE_UNITS if fmt.startswith(u, i)), None)
        if unit:
            i += len(unit)
        elif fmt[i] in DATE_SEPARATORS:
            i += 1
        else:
            raise TemplateError(f"bad date format character {fmt[i]!r}", offset + i)


def _check_path(template: str) -> None:
    offset = 0
    segments = template.split("/")
    for seg in segments:
        if not seg:
            raise TemplateError("empty path segment", offset)
        if seg in (".", ".."):
            raise TemplateError(f"segment {seg!r} is not allowed", offset)
        offset += len(seg) + 1


def _check_file(template: str, parts: list[tuple]) -> None:
    if "/" in template:
        raise TemplateError("'/' in a file template", template.index("/"))
    if not parts or parts[0][:2] != ("tok", "date"):
        raise TemplateError("a file template must begin with a date token", 0)
    if re.search(r"\.(pdf|jpe?g|png)$", template, re.IGNORECASE):
        raise TemplateError("a file template carries no extension", len(template) - 4)


def fiscal_year(d: date, fy_end_month: int, fy_end_day: int) -> int:
    return d.year if (d.month, d.day) <= (fy_end_month, fy_end_day) else d.year + 1


def format_date(d: date, fmt: str) -> str:
    out, i = [], 0
    while i < len(fmt):
        unit = next((u for u in DATE_UNITS if fmt.startswith(u, i)), None)
        if unit:
            out.append(
                {"YYYY": f"{d.year:04d}", "YY": f"{d.year % 100:02d}", "MM": f"{d.month:02d}", "DD": f"{d.day:02d}"}[
                    unit
                ]
            )
            i += len(unit)
        else:
            out.append(fmt[i])
            i += 1
    return "".join(out)


def slug(value: str) -> str:
    plain = "".join(c for c in unicodedata.normalize("NFKD", value) if unicodedata.category(c) != "Mn")
    plain = re.sub(r"[^A-Za-z0-9.]+", "-", plain)
    return re.sub(r"-+", "-", plain).strip("-.")


def _cut_bytes(text: str, max_chars: int, max_bytes: int) -> str:
    text = text[:max_chars]
    while len(text.encode("utf-8")) > max_bytes:
        text = text[:-1]
    return text


def folder_segment(value: str) -> str:
    value = unicodedata.normalize("NFC", value)
    value = "".join("-" if c in FORBIDDEN or ord(c) < 32 or ord(c) == 127 else c for c in value)
    value = re.sub(r"\s+", " ", value).strip(" .")
    return _cut_bytes(value, 80, 255).strip(" .")


def file_stem(concatenated: str) -> str:
    stem = re.sub(r"[_-]+", lambda m: "_" if "_" in m.group(0) else "-", concatenated).strip("_-.")
    if len(stem) > STEM_MAX:
        cut = max(stem.rfind("_", 0, STEM_MAX + 1), stem.rfind("-", 0, STEM_MAX + 1))
        stem = stem[:cut] if cut >= STEM_CUT_MIN else stem[:STEM_MAX]
        stem = stem.strip("_-.")
    return stem


@dataclass
class Registry:
    language: str
    entities: dict
    categories: dict
    templates: list

    @classmethod
    def from_practice(cls, practice: dict) -> "Registry":
        return cls(
            language=practice["practice"]["filing_language"],
            entities={e["key"]: e for e in practice["entities"]},
            categories={c["id"]: c for c in practice["categories"]},
            templates=practice["templates"],
        )

    def template_for(self, category: str, entity: str) -> dict:
        found = {t.get("entity"): t for t in self.templates if t["category"] == category}
        return found.get(entity) or found[None]


@dataclass
class Doc:
    entity: str
    category: str
    subcategory: str | None = None
    unit: str | None = None
    counterparty: str | None = None
    issuer: str | None = None
    reference: str | None = None
    doc_date: date | None = None
    period_end: date | None = None
    arrived_on: date | None = None
    mime_type: str = "application/pdf"
    path_template: str | None = None
    file_template: str | None = None


@dataclass
class Rendered:
    path: str | None
    file_name: str | None
    fiscal_year: int | None
    penalty: int = 0
    fallbacks: dict = field(default_factory=dict)


def _values(reg: Registry, doc: Doc) -> tuple[dict, dict, dict]:
    entity = reg.entities[doc.entity]
    lang = entity.get("filing_language") or reg.language
    fy_end = (entity["fy_end_month"], entity["fy_end_day"])
    fallbacks: dict[str, int] = {}

    def year() -> str:
        if doc.doc_date:
            return str(doc.doc_date.year)
        if doc.period_end:
            fallbacks["year"] = 10
            return str(doc.period_end.year)
        fallbacks["year"] = 20
        return str(doc.arrived_on.year)

    def fy() -> str:
        if doc.period_end:
            return str(fiscal_year(doc.period_end, *fy_end))
        if doc.doc_date:
            fallbacks["fy"] = 10
            return str(fiscal_year(doc.doc_date, *fy_end))
        fallbacks["fy"] = 20
        return str(fiscal_year(doc.arrived_on, *fy_end))

    sub_label = ""
    if doc.subcategory:
        sub = next(s for s in reg.categories[doc.category]["subcategories"] if s["key"] == doc.subcategory)
        sub_label = sub["labels"][lang]
    values = {
        "entity": entity["folder_name"],
        "category": reg.categories[doc.category]["labels"][lang],
        "sub": sub_label,
        "counterparty": doc.counterparty or "",
        "issuer": doc.issuer or doc.counterparty or "",
        "reference": doc.reference or "",
    }
    lazy = {"year": year, "fy": fy}
    return values, lazy, fallbacks


def render(reg: Registry, doc: Doc) -> Rendered:
    entity = reg.entities[doc.entity]
    tpl = reg.template_for(doc.category, doc.entity)
    path_parts = parse(doc.path_template or tpl["path_template"], "path")
    file_parts = parse(doc.file_template or tpl["file_template"], "file")
    values, lazy, fallbacks = _values(reg, doc)
    unit_label = None
    if doc.unit:
        unit_label = next(u["label"] for u in entity["sub_units"] if u["key"] == doc.unit)

    def value_of(name: str, fmt: str | None) -> str:
        if name == "date":
            if doc.doc_date:
                return format_date(doc.doc_date, fmt or "YYYY-MM-DD")
            fallbacks["date"] = 20
            return format_date(doc.arrived_on, fmt or "YYYY-MM-DD")
        return lazy[name]() if name in lazy else values[name]

    segments: list[str] = []
    for seg in _split_segments(path_parts):
        if seg == [("tok", "entity", None)] and unit_label:
            segments += [values["entity"], unit_label]
            continue
        segments.append("".join(p[1] if p[0] == "lit" else value_of(p[1], p[2]) for p in seg))
    folders = [s for s in (folder_segment(s) for s in segments) if s]
    if not folders:
        raise NotRenderable("no path segment left")

    pieces = []
    for p in file_parts:
        pieces.append(re.sub(r"[^A-Za-z0-9._-]", "-", p[1]) if p[0] == "lit" else slug(value_of(p[1], p[2])))
    stem = file_stem("".join(pieces))
    if not stem:
        raise NotRenderable("empty file name")
    # fiscal_year is always computed, whatever the templates use
    fy_source = doc.period_end or doc.doc_date or doc.arrived_on
    return Rendered(
        path="/".join(folders),
        file_name=stem + MIME_EXT[doc.mime_type],
        fiscal_year=fiscal_year(fy_source, entity["fy_end_month"], entity["fy_end_day"]),
        penalty=sum(fallbacks.values()),
        fallbacks=fallbacks,
    )


def _split_segments(parts: list[tuple]) -> list[list[tuple]]:
    segments: list[list[tuple]] = [[]]
    for p in parts:
        if p[0] == "lit" and "/" in p[1]:
            chunks = p[1].split("/")
            for k, chunk in enumerate(chunks):
                if k:
                    segments.append([])
                if chunk:
                    segments[-1].append(("lit", chunk))
        else:
            segments[-1].append(p)
    return segments


def overlay_path() -> Path:
    return Path(os.environ.get("MONA_SEED_OVERLAY", OVERLAY_DEFAULT)).expanduser()


def load_overlay() -> dict | None:
    path = overlay_path()
    return yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else None


def resolve_refs(node, overlay: dict | None):
    """Replace {ref: a.b.c} with the overlay value; without one, names become "@<key>" and the rest None."""
    if isinstance(node, dict):
        if set(node) == {"ref"}:
            return _lookup(node["ref"], overlay)
        return {k: resolve_refs(v, overlay) for k, v in node.items()}
    if isinstance(node, list):
        return [resolve_refs(v, overlay) for v in node]
    return node


def _lookup(ref: str, overlay: dict | None):
    parts = ref.split(".")
    if overlay is not None:
        cur = overlay
        for part in parts:
            cur = cur[part]
        return cur
    if parts[-1] in {"short_name", "display_name"}:
        return "@" + parts[-2]
    return [] if parts[-1] in {"aliases", "addresses"} else None


def load_practice(overlay: dict | None = None) -> dict:
    raw = yaml.safe_load((SEED_DIR / "practice.yaml").read_text(encoding="utf-8"))
    return resolve_refs(raw, overlay)


def load_rules(name: str = "rules.yaml") -> dict:
    return yaml.safe_load((SEED_DIR / name).read_text(encoding="utf-8"))

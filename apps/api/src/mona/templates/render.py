"""C5 §8.2–§8.4 rendering: a pure function of (templates, document values, registry, settings)."""

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from mona.templates.grammar import DATE_UNITS, Part, Token, parse

PARIS = ZoneInfo("Europe/Paris")
EXTENSIONS = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png"}
SEGMENT_CHARS = 80
SEGMENT_BYTES = 255
STEM_MAX = 116
STEM_CUT_MIN = 40
FALLBACK_NEAR = 10
FALLBACK_FAR = 20

_UNSAFE_SEGMENT = re.compile(r'[\\/:*?"<>|\x00-\x1f\x7f]')
_WS = re.compile(r"\s+")
_SLUG_RUN = re.compile(r"[^A-Za-z0-9.]+")
_LITERAL_CHAR = re.compile(r"[^A-Za-z0-9._-]")
_SEP_RUN = re.compile(r"[_-]+")


class NotRenderable(ValueError):
    """No path can be rendered (C5 §9.3 reason `entity`)."""


@dataclass(frozen=True)
class EntityInfo:
    key: str
    folder_name: str
    fy_end_month: int = 12
    fy_end_day: int = 31
    filing_language: str | None = None


@dataclass(frozen=True)
class RenderValues:
    entity: EntityInfo | None
    arrived_at: datetime | date
    language: str = "fr"
    sub_unit_label: str | None = None
    category_labels: Mapping[str, str] | None = None
    subcategory_labels: Mapping[str, str] | None = None
    counterparty: str | None = None
    issuer: str | None = None
    reference: str | None = None
    doc_date: date | None = None
    period_end: date | None = None
    mime_type: str = "application/pdf"


@dataclass(frozen=True)
class Rendered:
    folders: tuple[str, ...]
    file_name: str
    fiscal_year: int
    fallbacks: Mapping[str, int] = field(default_factory=dict)

    @property
    def folder(self) -> str:
        return "/".join(self.folders)

    @property
    def path(self) -> str:
        return f"{self.folder}/{self.file_name}"

    @property
    def penalty(self) -> int:
        return sum(self.fallbacks.values())


def paris_date(value: datetime | date) -> date:
    if isinstance(value, datetime):
        aware = value if value.tzinfo else value.replace(tzinfo=UTC)
        return aware.astimezone(PARIS).date()
    return value


def fiscal_year(d: date, fy_end_month: int, fy_end_day: int) -> int:
    """Named after the calendar year the fiscal year ends in (C5 §8.2)."""
    return d.year if (d.month, d.day) <= (fy_end_month, fy_end_day) else d.year + 1


def format_date(d: date, fmt: str) -> str:
    units = {"YYYY": f"{d.year:04d}", "YY": f"{d.year % 100:02d}", "MM": f"{d.month:02d}"}
    units["DD"] = f"{d.day:02d}"
    out, i = [], 0
    while i < len(fmt):
        unit = next((u for u in DATE_UNITS if fmt.startswith(u, i)), None)
        out.append(units[unit] if unit else fmt[i])
        i += len(unit) if unit else 1
    return "".join(out)


def folder_segment(value: str) -> str:
    """C5 §8.3: accents kept, unsafe characters to `-`, capped at 80 chars / 255 bytes."""
    s = unicodedata.normalize("NFC", value)
    s = _UNSAFE_SEGMENT.sub("-", s)
    s = _WS.sub(" ", s).strip(" .")
    s = s[:SEGMENT_CHARS]
    while len(s.encode("utf-8")) > SEGMENT_BYTES:
        s = s[:-1]
    return s.strip(" .")


def slug(value: str) -> str:
    """C5 §8.4.1: a token value for a file name, diacritics dropped."""
    s = unicodedata.normalize("NFKD", value)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = _SLUG_RUN.sub("-", s)
    return re.sub(r"-+", "-", s).strip("-.")


def file_stem(concatenated: str) -> str:
    """C5 §8.4.3–4: separator runs folded, capped at 116 characters."""
    s = _SEP_RUN.sub(lambda m: "_" if "_" in m.group(0) else "-", concatenated).strip("_-.")
    if len(s) > STEM_MAX:
        cut = max(s.rfind("_", 0, STEM_MAX + 1), s.rfind("-", 0, STEM_MAX + 1))
        s = (s[:cut] if cut >= STEM_CUT_MIN else s[:STEM_MAX]).strip("_-.")
    return s


def _segments(parts: list[Part]) -> list[list[Part]]:
    out: list[list[Part]] = [[]]
    for p in parts:
        if isinstance(p, str):
            chunks = p.split("/")
            for k, chunk in enumerate(chunks):
                if k:
                    out.append([])
                if chunk:
                    out[-1].append(chunk)
        else:
            out[-1].append(p)
    return out


class _Values:
    def __init__(self, v: RenderValues):
        if v.entity is None:
            raise NotRenderable("no entity")
        self.v = v
        self.entity = v.entity
        self.lang = v.entity.filing_language or v.language
        self.arrived = paris_date(v.arrived_at)
        self.fallbacks: dict[str, int] = {}

    def _fy(self, d: date) -> int:
        return fiscal_year(d, self.entity.fy_end_month, self.entity.fy_end_day)

    def _chain(self, token: str, first: date | None, second: date | None) -> date:
        if first is not None:
            return first
        if second is not None:
            self.fallbacks[token] = FALLBACK_NEAR
            return second
        self.fallbacks[token] = FALLBACK_FAR
        return self.arrived

    def value(self, t: Token) -> str:
        v = self.v
        match t.name:
            case "entity":
                return self.entity.folder_name
            case "year":
                return str(self._chain("year", v.doc_date, v.period_end).year)
            case "fy":
                return str(self._fy(self._chain("fy", v.period_end, v.doc_date)))
            case "category":
                if v.category_labels is None:
                    raise NotRenderable("no category")
                return v.category_labels[self.lang]
            case "sub":
                return v.subcategory_labels[self.lang] if v.subcategory_labels else ""
            case "counterparty":
                return v.counterparty or ""
            case "issuer":
                return v.issuer or v.counterparty or ""
            case "reference":
                return v.reference or ""
            case "date":
                d = v.doc_date
                if d is None:
                    self.fallbacks["date"] = FALLBACK_FAR
                    d = self.arrived
                return format_date(d, t.format or "YYYY-MM-DD")
        raise AssertionError(t.name)

    def document_fiscal_year(self) -> int:
        return self._fy(self.v.period_end or self.v.doc_date or self.arrived)


def document_fiscal_year(
    entity: EntityInfo | None,
    period_end: date | None,
    doc_date: date | None,
    arrived_at: datetime | date,
) -> int | None:
    """`documents.fiscal_year` (C5 §8.2); null without an entity."""
    if entity is None:
        return None
    d = period_end or doc_date or paris_date(arrived_at)
    return fiscal_year(d, entity.fy_end_month, entity.fy_end_day)


def render(path_template: str, file_template: str, v: RenderValues) -> Rendered:
    """Render folders and file name; raises NotRenderable when no path is left."""
    values = _Values(v)
    folders: list[str] = []
    for seg in _segments(parse(path_template, "path")):
        whole_entity = len(seg) == 1 and isinstance(seg[0], Token) and seg[0].name == "entity"
        if whole_entity and v.sub_unit_label:
            folders += [values.entity.folder_name, v.sub_unit_label]
            continue
        folders.append("".join(p if isinstance(p, str) else values.value(p) for p in seg))
    folders = [s for s in map(folder_segment, folders) if s]
    if not folders:
        raise NotRenderable("the path renders no segment")
    pieces = [
        _LITERAL_CHAR.sub("-", p) if isinstance(p, str) else slug(values.value(p))
        for p in parse(file_template, "file")
    ]
    stem = file_stem("".join(pieces))
    return Rendered(
        folders=tuple(folders),
        file_name=stem + EXTENSIONS[v.mime_type],
        fiscal_year=values.document_fiscal_year(),
        fallbacks=dict(values.fallbacks),
    )

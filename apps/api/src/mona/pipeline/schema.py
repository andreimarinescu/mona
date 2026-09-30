"""C5 §5.2: the per-request output schema, its validation, and the stored value forms."""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

PROMPT_VERSION = "c5-v1"
FIELD_KEYS = ("entity", "counterparty", "issuer", "reference", "doc_type", "doc_date",
              "period_start", "period_end", "amount", "due_date", "addressee")  # fmt: skip
DATE_FIELDS = ("doc_date", "period_start", "period_end", "due_date")
TEXT_MAX = {"counterparty": 160, "issuer": 160, "reference": 60, "doc_type": 80, "addressee": 160}
DATE = {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$", "maxLength": 10}
_WS = re.compile(r"\s+")


def _ev(value: dict[str, Any], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    props = {"value": value, **(extra or {}),
             "quote": {"type": "string", "maxLength": 160},
             "page": {"type": "integer", "minimum": 1}}  # fmt: skip
    return {"type": "object", "properties": props, "required": list(props),
            "additionalProperties": False}  # fmt: skip


def _nullable(s: dict[str, Any]) -> dict[str, Any]:
    return {"anyOf": [s, {"type": "null"}]}


def build(
    categories: Sequence[str], subcategories: Sequence[str], entities: Sequence[str]
) -> dict[str, Any]:
    """`subcategories` as `<category>.<key>`; `entities` without the Visitors entity."""
    props: dict[str, Any] = {
        "title": {"type": "string", "maxLength": 120},
        "category": {"type": "string", "enum": [*categories, "unknown"]},
        "subcategory": _nullable({"type": "string", "enum": list(subcategories)})
        if subcategories
        else {"type": "null"},
        "entity": _nullable(_ev({"type": "string", "enum": list(entities)}))
        if entities
        else {"type": "null"},
    }
    for key in ("counterparty", "issuer", "reference", "doc_type"):
        props[key] = _nullable(_ev({"type": "string", "maxLength": TEXT_MAX[key]}))
    for key in ("doc_date", "period_start", "period_end"):
        props[key] = _nullable(_ev(DATE))
    currency = {"type": "string", "pattern": "^[A-Z]{3}$", "maxLength": 3}
    props["amount"] = _nullable(_ev({"type": "number"}, {"currency": currency}))
    props["due_date"] = _nullable(_ev(DATE))
    props["addressee"] = _nullable(_ev({"type": "string", "maxLength": TEXT_MAX["addressee"]}))
    props["confidence"] = {"type": "number", "minimum": 0, "maximum": 1}
    props["reason"] = {"type": "string", "maxLength": 250}
    return {"type": "object", "properties": props, "required": list(props),
            "additionalProperties": False}  # fmt: skip


_TYPES = {
    "object": lambda v: isinstance(v, dict),
    "string": lambda v: isinstance(v, str),
    "number": lambda v: isinstance(v, int | float) and not isinstance(v, bool),
    "integer": lambda v: (
        (isinstance(v, int) and not isinstance(v, bool))
        or (isinstance(v, float) and v.is_integer())
    ),
    "null": lambda v: v is None,
}


def errors(value: Any, schema: Mapping[str, Any], path: str = "$") -> list[str]:
    """Validation against the subset of JSON Schema `build` uses."""
    if "anyOf" in schema:
        if any(not errors(value, s, path) for s in schema["anyOf"]):
            return []
        return [f"{path}: matches no alternative"]
    t = schema.get("type")
    if t and not _TYPES[t](value):
        return [f"{path}: not {t}"]
    out = []
    if "enum" in schema and value not in schema["enum"]:
        out.append(f"{path}: not in enum")
    if isinstance(value, str):
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            out.append(f"{path}: longer than {schema['maxLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            out.append(f"{path}: does not match {schema['pattern']}")
    if t in ("number", "integer"):
        if "minimum" in schema and value < schema["minimum"]:
            out.append(f"{path}: below {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            out.append(f"{path}: above {schema['maximum']}")
    if t == "object":
        props = schema.get("properties", {})
        out += [f"{path}.{k}: missing" for k in schema.get("required", []) if k not in value]
        if schema.get("additionalProperties") is False:
            out += [f"{path}.{k}: not allowed" for k in value if k not in props]
        for k, s in props.items():
            if k in value:
                out += errors(value[k], s, f"{path}.{k}")
    return out


def strings_bounded(schema: Mapping[str, Any]) -> bool:
    """C5 §5.2: every string in the schema has an `enum` or a `maxLength`."""
    if schema.get("type") == "string" and "enum" not in schema and "maxLength" not in schema:
        return False
    subs = [*schema.get("anyOf", []), *schema.get("properties", {}).values()]
    return all(strings_bounded(s) for s in subs)


@dataclass(frozen=True)
class Field:
    key: str
    value: str
    quote: str
    page: int
    currency: str | None = None
    amount: Decimal | None = None
    day: date | None = None


@dataclass(frozen=True)
class Output:
    title: str
    category: str
    subcategory: str | None
    fields: dict[str, Field]
    confidence: float
    reason: str


def collapse(s: str) -> str:
    return _WS.sub(" ", s).strip()


def parse_date(s: str) -> date | None:
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def cents(v: float | int | Decimal) -> Decimal:
    return Decimal(str(v)).quantize(Decimal("0.01"), ROUND_HALF_UP)


def clean(raw: Mapping[str, Any]) -> Output:
    """Stored forms (§5.2): a subcategory of another category is dropped, impossible dates and
    empty values are treated as absent, text is trimmed with whitespace runs collapsed."""
    category = raw["category"]
    sub = raw.get("subcategory")
    subcategory = sub.split(".", 1)[1] if sub and sub.split(".", 1)[0] == category else None
    fields: dict[str, Field] = {}
    for key in FIELD_KEYS:
        f = raw.get(key)
        if not f:
            continue
        page, quote = int(f["page"]), f["quote"]
        if key in DATE_FIELDS:
            d = parse_date(f["value"])
            if d is not None:
                fields[key] = Field(key, d.isoformat(), quote, page, day=d)
        elif key == "amount":
            amount = cents(f["value"])
            fields[key] = Field(key, f"{amount:.2f}", quote, page, f["currency"], amount)
        else:
            value = collapse(f["value"])
            if value:
                fields[key] = Field(key, value, quote, page)
    return Output(collapse(raw.get("title") or ""), category, subcategory, fields,
                  float(raw["confidence"]), raw.get("reason") or "")  # fmt: skip

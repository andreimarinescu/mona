"""C6 §4.4: the pass-2 output schema, built per request, and a validator for its subset."""

from typing import Any

from sqlalchemy import Connection, select

from mona.db.models import Base
from mona.interviews.config import MAX_QUESTIONS
from mona.rules.grammar import OPS

T = Base.metadata.tables
CONDITION_FIELDS = list(OPS)
ALL_OPS = sorted({op for ops in OPS.values() for op in ops})
OPTION_IDS = ["a", "b", "c"]


def _obj(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def _str(max_length: int) -> dict[str, Any]:
    return {"type": "string", "maxLength": max_length}


def _enum(values: list[str]) -> dict[str, Any]:
    return {"type": "string", "enum": values}


def _nullable_enum(*groups: list[str]) -> dict[str, Any]:
    return {"anyOf": [*(_enum(g) for g in groups if g), {"type": "null"}]}


def registry_enums(conn: Connection) -> dict[str, list[str]]:
    e, s, c, sc = T["entities"], T["sub_units"], T["categories"], T["subcategories"]
    ents = {
        r.id: r.key
        for r in conn.execute(
            select(e.c.id, e.c.key).where(e.c.purge_after_hours.is_(None)).order_by(e.c.key)
        )
    }
    units = [
        f"{ents[r.entity_id]}/{r.key}"
        for r in conn.execute(select(s.c.entity_id, s.c.key).order_by(s.c.key))
        if r.entity_id in ents
    ]
    return {
        "entities": list(ents.values()),
        "units": sorted(units),
        "categories": list(conn.execute(select(c.c.id).order_by(c.c.id)).scalars()),
        "subcategories": [
            f"{r.category_id}.{r.key}"
            for r in conn.execute(
                select(sc.c.category_id, sc.c.key).order_by(sc.c.category_id, sc.c.key)
            )
        ],
    }


def build(aliases: list[str], enums: dict[str, list[str]], *, seed: bool = False) -> dict:
    """The strict schema: every string has an `enum` or a `maxLength`; aliases are an enum."""
    value = {
        "anyOf": [
            _str(120),
            {"type": "array", "items": _str(60), "minItems": 1, "maxItems": 6},
            {"type": "number"},
            {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
        ]
    }
    condition = _obj({"field": _enum(CONDITION_FIELDS), "op": _enum(ALL_OPS), "value": value})
    action = _obj(
        {
            "entity": _enum(enums["entities"]),
            "unit": _nullable_enum(enums["units"], ["from_person"]),
            "category": _nullable_enum(enums["categories"]),
            "subcategory": _nullable_enum(enums["subcategories"]),
        }
    )
    branch = _obj(
        {
            "conditions": {"type": "array", "items": condition, "minItems": 1, "maxItems": 4},
            "action": action,
        }
    )
    option = _obj(
        {
            "id": _enum(OPTION_IDS),
            "label": _str(90),
            "rule_draft": _obj(
                {
                    "kind": _enum(["always", "depends", "ask"]),
                    "discriminator": _nullable_enum(CONDITION_FIELDS),
                    "branches": {"type": "array", "items": branch, "minItems": 0, "maxItems": 4},
                }
            ),
        }
    )
    alias = _enum(aliases)
    question = _obj(
        {
            "text": _str(300),
            "affected": {
                "type": "array",
                "items": alias,
                "minItems": 0 if seed else 1,
                "maxItems": 40,
            },
            "evidence": {
                "type": "array",
                "items": _obj({"doc": alias, "quote": _str(160)}),
                "minItems": 0,
                "maxItems": 0 if seed else 3,
            },
            "options": {"type": "array", "items": option, "minItems": 2, "maxItems": 3},
            "suggested": _enum(OPTION_IDS),
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        }
    )
    return _obj(
        {
            "questions": {
                "type": "array",
                "items": question,
                "minItems": 1,
                "maxItems": MAX_QUESTIONS,
            }
        }
    )


def _type_ok(value: Any, t: str) -> bool:
    match t:
        case "object":
            return isinstance(value, dict)
        case "array":
            return isinstance(value, list)
        case "string":
            return isinstance(value, str)
        case "number":
            return isinstance(value, int | float) and not isinstance(value, bool)
        case "integer":
            return isinstance(value, int) and not isinstance(value, bool)
        case "boolean":
            return isinstance(value, bool)
        case "null":
            return value is None
    return False


def errors(value: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    """The JSON Schema subset `build` uses; an empty list means valid."""
    if "anyOf" in schema:
        if any(not errors(value, s, path) for s in schema["anyOf"]):
            return []
        return [f"{path}: matches no alternative"]
    t = schema.get("type")
    if t and not _type_ok(value, t):
        return [f"{path}: expected {t}"]
    out: list[str] = []
    if "enum" in schema and value not in schema["enum"]:
        out.append(f"{path}: not one of the allowed values")
    if t == "string" and "maxLength" in schema and len(value) > schema["maxLength"]:
        out.append(f"{path}: longer than {schema['maxLength']}")
    if t == "number":
        if "minimum" in schema and value < schema["minimum"]:
            out.append(f"{path}: below {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            out.append(f"{path}: above {schema['maximum']}")
    if t == "array":
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", 1e9):
            out.append(f"{path}: wrong number of items")
        for i, item in enumerate(value):
            out += errors(item, schema.get("items", {}), f"{path}[{i}]")
    if t == "object":
        props = schema.get("properties", {})
        missing = [k for k in schema.get("required", []) if k not in value]
        extra = (
            [k for k in value if k not in props]
            if schema.get("additionalProperties") is False
            else []
        )
        out += [f"{path}.{k}: missing" for k in missing] + [
            f"{path}.{k}: not allowed" for k in extra
        ]
        for k, sub in props.items():
            if k in value:
                out += errors(value[k], sub, f"{path}.{k}")
    return out


def strings_bounded(schema: Any) -> bool:
    """C5 §5.2: every string in the schema has an `enum` or a `maxLength`."""
    if isinstance(schema, dict):
        if schema.get("type") == "string" and "enum" not in schema and "maxLength" not in schema:
            return False
        return all(strings_bounded(v) for v in schema.values())
    if isinstance(schema, list):
        return all(strings_bounded(v) for v in schema)
    return True

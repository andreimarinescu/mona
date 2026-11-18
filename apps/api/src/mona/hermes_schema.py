"""MCP tool schemas as the pinned Hermes image sends them: a port of its
`tools/mcp_tool_schema.py::_convert_mcp_schema` and `_normalize_mcp_input_schema`.

Key order is kept as Hermes builds it: llama-server renders the tool JSON into the prompt."""

import hashlib
import re
from collections.abc import Callable
from typing import Any

PREFIX = "mcp__"
NAME_MAX, NAME_HASH = 64, 8
_UNION_KEYS = ("anyOf", "oneOf")
_UNION_META_KEYS = ("title", "description", "default", "examples")
_SCHEMA_MAP_KEYS = ("properties", "patternProperties", "$defs", "definitions", "dependentSchemas")
_CONST_TYPES: dict[type, str] = {bool: "boolean", int: "integer", float: "number", str: "string"}


def _rewrite(schema: Any, fn: Callable[[dict], Any]) -> Any:
    if isinstance(schema, list):
        return [_rewrite(item, fn) for item in schema]
    if not isinstance(schema, dict):
        return schema
    return fn({k: _rewrite(v, fn) for k, v in schema.items()})


def _rewrite_local_refs(node: Any) -> Any:
    if isinstance(node, list):
        return [_rewrite_local_refs(item) for item in node]
    if not isinstance(node, dict):
        return node
    out = {}
    for key, value in node.items():
        if key in ("properties", "patternProperties") and isinstance(value, dict):
            out[key] = {name: _rewrite_local_refs(s) for name, s in value.items()}
        else:
            out["$defs" if key == "definitions" else key] = _rewrite_local_refs(value)
    ref = out.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/definitions/"):
        out["$ref"] = "#/$defs/" + ref[len("#/definitions/") :]
    return out


def _is_null(item: Any) -> bool:
    return isinstance(item, dict) and item.get("type") == "null"


def _carry_meta(outer: dict, replacement: dict, *, skip_default_on_ref: bool) -> None:
    for key in _UNION_META_KEYS:
        if key in outer and key not in replacement:
            if not (skip_default_on_ref and key == "default" and "$ref" in replacement):
                replacement[key] = outer[key]


def _strip_nullable_unions(schema: Any) -> Any:
    def collapse(node: dict) -> Any:
        for key in _UNION_KEYS:
            variants = node.get(key)
            if not isinstance(variants, list):
                continue
            rest = [item for item in variants if not _is_null(item)]
            if len(rest) == 1 and len(rest) != len(variants):
                replacement = dict(rest[0]) if isinstance(rest[0], dict) else {}
                replacement.setdefault("nullable", True)
                _carry_meta(node, replacement, skip_default_on_ref=True)
                return _rewrite(replacement, collapse)
        return node

    return _rewrite(schema, collapse)


def _const_type(branch: Any) -> str | None:
    if not isinstance(branch, dict) or "const" not in branch:
        return None
    if set(branch) - {"const", "type", "title", "description"}:
        return None
    json_type = _CONST_TYPES.get(type(branch["const"]))
    return json_type if branch.get("type") in (None, json_type) else None


def _collapse_const_unions(schema: Any) -> Any:
    def collapse(node: dict) -> Any:
        for key in _UNION_KEYS:
            variants = node.get(key)
            if not isinstance(variants, list) or not variants:
                continue
            nulls = [i for i in variants if _is_null(i) and "const" not in i]
            consts = [i for i in variants if i not in nulls]
            if len(nulls) > 1 or not consts:
                continue
            types = {_const_type(i) for i in consts}
            if len(types) != 1 or None in types:
                continue
            replacement: dict = {"type": types.pop(), "enum": [i["const"] for i in consts]}
            if nulls:
                replacement["nullable"] = True
            _carry_meta(node, replacement, skip_default_on_ref=False)
            return replacement
        return node

    return _rewrite(schema, collapse)


def _repair_object_shape(node: Any, *, root: bool = False) -> Any:
    if isinstance(node, list):
        return [_repair_object_shape(item) for item in node]
    if not isinstance(node, dict):
        return node
    out = {}
    for key, value in node.items():
        if key in _SCHEMA_MAP_KEYS and isinstance(value, dict):
            out[key] = {name: _repair_object_shape(s) for name, s in value.items()}
        else:
            out[key] = _repair_object_shape(value)
    if root or "properties" in out or "type" in node:
        if not out.get("type") and ("properties" in out or "required" in out):
            out["type"] = "object"
        if out.get("type") == "object":
            if not isinstance(out.get("properties"), dict):
                out["properties"] = {}
            required, props = out.get("required"), out.get("properties") or {}
            out["required"] = (
                [r for r in required if isinstance(r, str) and r in props]
                if isinstance(required, list)
                else []
            )
    return out


def normalize_input_schema(schema: dict | None) -> dict:
    if not schema:
        return {"type": "object", "properties": {}}
    out = _rewrite_local_refs(schema)
    out = _strip_nullable_unions(out)
    out = _collapse_const_unions(out)
    out = _repair_object_shape(out, root=True)
    if not isinstance(out, dict):
        return {"type": "object", "properties": {}}
    if out.get("type") == "object" and "properties" not in out:
        out = {**out, "properties": {}}
    return out


def tool_name(server: str, tool: str) -> str:
    full = f"{PREFIX}{re.sub(r'[^A-Za-z0-9_]', '_', server)}__{re.sub(r'[^A-Za-z0-9_]', '_', tool)}"
    if len(full) <= NAME_MAX:
        return full
    suffix = "_" + hashlib.sha256(full.encode()).hexdigest()[:NAME_HASH]
    return full[: NAME_MAX - len(suffix)] + suffix


def openai_tool(server: str, name: str, description: str | None, schema: dict | None) -> dict:
    return {
        "type": "function",
        "function": {
            "name": tool_name(server, name),
            "description": description or f"MCP tool {name} from {server}",
            "parameters": normalize_input_schema(schema),
        },
    }

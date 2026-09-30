"""Validator for the C5 §10 rules.yaml schema and the §4 grammar (seed and learned tiers)."""

import re

import templates

SLUG = re.compile(r"^[a-z][a-z0-9-]{1,39}$")
OPS = {
    "counterparty": {"equals", "in", "contains"},
    "text": {"contains", "contains_any", "contains_all"},
    "doc_type": {"equals", "in", "contains"},
    "category": {"equals", "in"},
    "entity": {"equals", "in"},
    "addressee": {"contains", "is_person", "is_entity"},
    "person": {"mentions"},
    "iban": {"account", "entity"},
    "siren": {"equals", "in", "entity"},
    "amount": {"gt", "gte", "lt", "lte", "between"},
}
LIST_OPS = {"in", "contains_any", "contains_all"}
ACTION_KEYS = {"entity", "unit", "category", "subcategory", "counterparty", "path", "filename", "review"}
RULE_KEYS = {"key", "name", "state", "source", "priority", "conditions", "action"}
IBAN_LITERAL = re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){2,7}(?:[ ]?[A-Z0-9]{1,4})?\b")


def validate(doc: dict, practice: dict) -> list[str]:
    errors: list[str] = []
    if doc.get("schema") != "mona.rules/v1":
        errors.append("schema must be mona.rules/v1")
    rules = doc.get("rules")
    if not isinstance(rules, list) or not rules:
        return errors + ["rules must be a non-empty list"]
    known = _registry(practice)
    seen: set[str] = set()
    for rule in rules:
        where = str(rule.get("key"))
        if not SLUG.match(where) or where in seen:
            errors.append(f"{where}: key must be a unique slug")
        seen.add(where)
        for extra in set(rule) - RULE_KEYS:
            errors.append(f"{where}: unknown key {extra}")
        if not rule.get("name"):
            errors.append(f"{where}: name required")
        if rule.get("state", "active") not in {"draft", "active", "disabled"}:
            errors.append(f"{where}: bad state")
        if rule.get("source", "seed") not in {"seed", "interview", "correction"}:
            errors.append(f"{where}: bad source")
        if "priority" in rule and not isinstance(rule["priority"], int):
            errors.append(f"{where}: priority must be an integer")
        conditions = rule.get("conditions") or []
        if not 1 <= len(conditions) <= 8:
            errors.append(f"{where}: 1 to 8 conditions required")
        for cond in conditions:
            errors += [f"{where}: {e}" for e in _condition(cond, known)]
        errors += [f"{where}: {e}" for e in _action(rule.get("action") or {}, known, practice)]
    if IBAN_LITERAL.search(repr(doc).replace("'", " ")):
        errors.append("an IBAN literal appears in the file")
    return errors


def _registry(practice: dict) -> dict:
    return {
        "entities": {e["key"]: e for e in practice["entities"]},
        "people": {p["key"] for p in practice["people"]},
        "accounts": {a["key"] for a in practice["accounts"]},
        "counterparties": {c["key"] for c in practice["counterparties"]},
        "categories": {c["id"]: c for c in practice["categories"]},
    }


def _condition(cond: dict, known: dict) -> list[str]:
    field, op, value = cond.get("field"), cond.get("op"), cond.get("value")
    if set(cond) - {"field", "op", "value", "negate"}:
        return ["condition has unknown keys"]
    if field not in OPS or op not in OPS[field]:
        return [f"bad field/op {field}/{op}"]
    if "negate" in cond and not isinstance(cond["negate"], bool):
        return ["negate must be a boolean"]
    if op in LIST_OPS and not (isinstance(value, list) and value and all(isinstance(v, str) for v in value)):
        return [f"{field} {op} needs a list of strings"]
    if op == "between":
        return [] if isinstance(value, list) and len(value) == 2 else ["between needs [min, max]"]
    if op not in LIST_OPS and field != "amount" and not isinstance(value, str):
        return [f"{field} {op} needs a string"]
    refs = {
        ("counterparty", "equals"): "counterparties",
        ("counterparty", "in"): "counterparties",
        ("person", "mentions"): "people",
        ("addressee", "is_person"): "people",
        ("addressee", "is_entity"): "entities",
        ("iban", "account"): "accounts",
        ("iban", "entity"): "entities",
        ("siren", "entity"): "entities",
        ("entity", "equals"): "entities",
        ("entity", "in"): "entities",
        ("category", "equals"): "categories",
        ("category", "in"): "categories",
    }
    kind = refs.get((field, op))
    if kind:
        missing = [v for v in (value if isinstance(value, list) else [value]) if v not in known[kind]]
        return [f"{field} {op}: unresolved {kind} key {m}" for m in missing]
    if (field, op) == ("siren", "equals") and not re.fullmatch(r"\d{9}", value):
        return ["siren equals needs 9 digits"]
    return []


def _action(action: dict, known: dict, practice: dict) -> list[str]:
    errors = [f"unknown action key {k}" for k in set(action) - ACTION_KEYS]
    if not set(action) & {"entity", "category", "review"}:
        errors.append("action needs entity, category or review")
    entity = known["entities"].get(action.get("entity")) if "entity" in action else None
    if "entity" in action:
        if entity is None:
            errors.append(f"unresolved entity {action['entity']}")
        elif entity.get("purge_after_hours"):
            errors.append("an action can't name the Visitors entity")
    if "unit" in action:
        unit = action["unit"]
        if "entity" not in action or entity is None:
            errors.append("unit requires a resolvable entity")
        elif unit == {"from": "person"}:
            if not any(u.get("person") for u in entity.get("sub_units", [])):
                errors.append("unit from person needs person-linked sub-units")
        elif unit not in {u["key"] for u in entity.get("sub_units", [])}:
            errors.append(f"unknown sub-unit {unit}")
    category = action.get("category")
    if category and category not in known["categories"]:
        errors.append(f"unresolved category {category}")
    if "subcategory" in action:
        if not category:
            errors.append("subcategory needs the action's category in a seed file")
        elif action["subcategory"] not in {s["key"] for s in known["categories"][category]["subcategories"]}:
            errors.append(f"subcategory {action['subcategory']} not under {category}")
    if "counterparty" in action and action["counterparty"] not in known["counterparties"]:
        errors.append(f"unresolved counterparty {action['counterparty']}")
    for key, kind in (("path", "path"), ("filename", "file")):
        if key in action:
            try:
                templates.parse(action[key], kind)
            except templates.TemplateError as exc:
                errors.append(f"{key}: {exc}")
    if "review" in action and action["review"] is not True:
        errors.append("review must be true")
    return errors

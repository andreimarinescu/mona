import re

import pytest
from pydantic import ValidationError

from mona.rules.grammar import OPS, Condition, Registry, RuleAction, RuleBody, RuleDraft, unresolved
from mona.rules.text import Names, render_condition, render_condition_text
from mona.templates import TemplateError, Token, parse

# --- templates (C5 §8.1) ---


def test_parse_path_and_file_templates():
    parts = parse("{entity}/Assurances/{counterparty}/{sub}/{year}", "path")
    assert parts[0] == Token("entity", None, 0) and parts[1] == "/Assurances/"
    file_parts = parse("{date:YYYY-MM-DD}_{counterparty}_{sub}_{reference}", "file")
    assert file_parts[0] == Token("date", "YYYY-MM-DD", 0)
    assert parse("{entity}/{fy} {entity}/Documents annuels", "path")


@pytest.mark.parametrize(
    ("template", "kind", "offset"),
    [
        ("{entity}/{amount}", "path", 9),  # unknown token
        ("{entity}/{year:YYYY}", "path", 9),  # format on a non-date token
        ("{date:YYYY/MM}_x", "file", 10),  # bad format
        ("{date:}_x", "file", 0),  # empty format
        ("{date:YYYY-MM-DD}_{sub", "file", 18),  # unclosed
        ("{date:YYYY}}", "file", 11),  # stray }
        ("{date:YYYY}_{sub{x}}", "file", 12),  # nested
        ("/{entity}/Banque", "path", 0),  # leading /
        ("{entity}/Banque/", "path", 16),  # trailing /
        ("{entity}//Banque", "path", 9),  # empty segment
        ("{entity}/../Banque", "path", 9),  # ..
        ("{entity}/./Banque", "path", 9),  # .
        ("{counterparty}_{date:YYYY}", "file", 0),  # not date first
        ("{date:YYYY}/x", "file", 11),  # / in a file template
        ("", "path", 0),
    ],
)
def test_template_errors_carry_offsets(template, kind, offset):
    with pytest.raises(TemplateError) as e:
        parse(template, kind)
    assert e.value.offset == offset


# --- conditions and actions (C5 §4.2, §4.5) ---

VALID_VALUES = {
    "str": "AGIPI",
    "strs": ["a", "b"],
    "siren": "123456789",
    "sirens": ["123456789"],
    "number": 100,
    "range": [10, 20.5],
}
INVALID_VALUES = {
    "str": ["x"],
    "strs": [],
    "siren": "12345678",
    "sirens": ["12345678"],
    "number": True,
    "range": [20, 10],
}
ALL_OPS = [(f, op, kind) for f, ops in OPS.items() for op, kind in ops.items()]


@pytest.mark.parametrize(("field", "op", "kind"), ALL_OPS)
def test_every_field_op_accepts_its_value_kind(field, op, kind):
    c = Condition(field=field, op=op, value=VALID_VALUES[kind])
    assert c.model_dump() == {"field": field, "op": op, "value": VALID_VALUES[kind]}
    with pytest.raises(ValidationError):
        Condition(field=field, op=op, value=INVALID_VALUES[kind])


def test_condition_rejects_unknown_field_op_and_keys():
    with pytest.raises(ValidationError):
        Condition(field="text", op="equals", value="x")
    with pytest.raises(ValidationError):
        Condition(field="colour", op="equals", value="x")
    with pytest.raises(ValidationError):
        Condition.model_validate({"field": "text", "op": "contains", "value": "x", "extra": 1})


def test_negate_serialises_only_when_true():
    assert (
        "negate" not in Condition(field="text", op="contains", value="x", negate=False).model_dump()
    )
    assert Condition(field="text", op="contains", value="x", negate=True).model_dump()["negate"]


def test_action_rules():
    a = RuleAction.model_validate({"entity": "personal", "unit": {"from": "person"}})
    assert a.model_dump() == {"entity": "personal", "unit": {"from": "person"}}
    assert RuleAction(review=True).model_dump() == {"review": True}
    for bad in [
        {},
        {"review": False},
        {"unit": "paul", "category": "tax"},
        {"entity": "x", "unit": {"from": "addressee"}},
        {"entity": "x", "path": "{entity}/{nope}"},
        {"entity": "x", "filename": "{sub}_{date:YYYY}"},
        {"entity": "x", "colour": "red"},
    ]:
        with pytest.raises(ValidationError):
            RuleAction.model_validate(bad)


def test_rule_body_condition_count():
    c = {"field": "text", "op": "contains", "value": "x"}
    RuleBody.model_validate({"conditions": [c] * 8, "action": {"entity": "e"}})
    for n in (0, 9):
        with pytest.raises(ValidationError):
            RuleBody.model_validate({"conditions": [c] * n, "action": {"entity": "e"}})


REGISTRY = Registry(
    entities={"cabinet", "personal", "visitors"},
    visitors_entity="visitors",
    sub_units={"personal": {"paul"}},
    people={"paul"},
    accounts={"lmnp-hello"},
    counterparties={"agipi"},
    categories={"insurance", "tax"},
    subcategories={"insurance": {"per"}},
)


def test_unresolved_references_are_all_listed():
    body = RuleBody.model_validate(
        {
            "conditions": [
                {"field": "entity", "op": "in", "value": ["cabinet", "ghost"]},
                {"field": "person", "op": "mentions", "value": "anna"},
                {"field": "iban", "op": "account", "value": "nope"},
                {"field": "category", "op": "equals", "value": "bank"},
                {"field": "counterparty", "op": "equals", "value": "Any Name Works"},
            ],
            "action": {
                "entity": "personal",
                "unit": "anna",
                "category": "insurance",
                "subcategory": "vie",
                "counterparty": "axa",
            },
        }
    )
    errors = unresolved(body, REGISTRY)
    assert len(errors) == 7, errors
    assert any("'ghost'" in e for e in errors) and any("'axa'" in e for e in errors)


def test_visitors_entity_is_not_a_rule_action():
    body = RuleBody.model_validate(
        {"conditions": [{"field": "text", "op": "contains", "value": "x"}],
         "action": {"entity": "visitors"}}
    )  # fmt: skip
    assert unresolved(body, REGISTRY) == [
        "action.entity: the Visitors entity can't be a rule action"
    ]


# --- RuleDraft (C1 §11.5, §12 test 11) ---

CPT = {"field": "counterparty", "op": "equals", "value": "Prévia"}


def _branch(entity="personal", **extra):
    return {"conditions": [CPT, *extra.get("more", [])], "action": {"entity": entity}}


def _person(key):
    return {"field": "addressee", "op": "is_person", "value": key}


def test_rule_draft_valid_shapes():
    RuleDraft.model_validate({"kind": "always", "discriminator": None, "branches": [_branch()]})
    RuleDraft.model_validate({"kind": "ask", "discriminator": None, "branches": []})
    RuleDraft.model_validate(
        {
            "kind": "depends",
            "discriminator": "addressee",
            "branches": [
                {"conditions": [CPT, _person("helene")], "action": {"entity": "cabinet"}},
                {
                    "conditions": [CPT, _person("paul")],
                    "action": {"entity": "personal", "unit": {"from": "person"}},
                },
            ],
        }
    )


@pytest.mark.parametrize(
    "draft",
    [
        {"kind": "always", "discriminator": None, "branches": [_branch(), _branch("cabinet")]},
        {"kind": "depends", "discriminator": None, "branches": [_branch(), _branch("cabinet")]},
        {"kind": "ask", "discriminator": None, "branches": [_branch()]},
        {"kind": "always", "discriminator": None,
         "branches": [{"conditions": [CPT], "action": {"category": "tax"}}]},
        {"kind": "depends", "discriminator": "addressee",
         "branches": [_branch(more=[_person("a")]), _branch("cabinet", more=[_person("a")])]},
        {"kind": "depends", "discriminator": "addressee",
         "branches": [_branch(more=[_person("a")])]},
        {"kind": "always", "discriminator": "addressee", "branches": [_branch()]},
    ],
)  # fmt: skip
def test_rule_draft_rejections(draft):
    with pytest.raises(ValidationError):
        RuleDraft.model_validate(draft)


# --- condition_text (C5 §4.7) ---

NAMES = Names(
    people={"paul": "Paul Marchand"},
    entities={"cabinet": "Cabinet Marchand"},
    accounts={"lmnp-hello": "Hello bank · LMNP •• 4821"},
    categories={"tax": {"en": "Taxes", "fr": "Impôts et taxes", "ro": "Impozite și taxe"}},
)
REF_VALUES = {"person": "paul", "account": "lmnp-hello", "entity": "cabinet", "category": "tax"}


def _value(field, op, kind):
    if field in ("category",):
        return ["tax", "tax"] if kind == "strs" else "tax"
    if (field, op) in {
        ("entity", "equals"),
        ("addressee", "is_entity"),
        ("iban", "entity"),
        ("siren", "entity"),
    }:
        return "cabinet"
    if field == "entity":
        return ["cabinet", "cabinet"]
    if (field, op) in {("addressee", "is_person"), ("person", "mentions")}:
        return "paul"
    if (field, op) == ("iban", "account"):
        return "lmnp-hello"
    return VALID_VALUES[kind]  # fmt: skip


@pytest.mark.parametrize(("field", "op", "kind"), ALL_OPS)
@pytest.mark.parametrize("negate", [False, True])
@pytest.mark.parametrize("lang", ["en", "fr", "ro"])
def test_every_condition_row_renders(field, op, kind, negate, lang):
    c = Condition(field=field, op=op, value=_value(field, op, kind), negate=negate)
    text = render_condition(c, lang, NAMES)
    assert text and not re.search(r"[{}]", text)
    negation = {"en": r"\b(not|n't)\b|n't", "fr": r"\b(pas|aucun)\b", "ro": r"\bnu\b"}[lang]
    assert bool(re.search(negation, text)) == negate, text
    for key, name in [("paul", "Paul Marchand"), ("cabinet", "Cabinet Marchand")]:
        if c.value == key:
            assert name in text


def test_condition_text_sentence():
    conditions = [
        Condition(field="counterparty", op="equals", value="OPCO"),
        Condition(field="text", op="contains_any", value=["plan d'épargne retraite", "PER"]),
        Condition(field="amount", op="gte", value=1284),
    ]
    text = render_condition_text(conditions, NAMES)
    assert text["en"] == (
        "When the counterparty is OPCO, the text mentions “plan d'épargne retraite” or “PER”"
        " and the amount is at least 1,284.00."
    )
    assert text["fr"] == (
        "Quand l'émetteur est OPCO, le texte mentionne « plan d'épargne retraite » ou « PER »"
        " et le montant est d'au moins 1 284,00."
    )
    assert text["ro"] == (
        "Când emitentul este OPCO, textul menționează „plan d'épargne retraite” sau „PER”"
        " și suma este de cel puțin 1.284,00."
    )

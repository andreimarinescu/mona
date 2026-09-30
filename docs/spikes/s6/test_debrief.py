# /// script
# requires-python = ">=3.12"
# dependencies = ["httpx", "jsonschema", "pytest"]
# ///
import copy
import json
import pathlib
import sys

import jsonschema
import pytest
from t6_debrief import check, question_schema

CLUSTER = json.loads((pathlib.Path(__file__).parent / "debrief" / "cluster.json").read_text())


def card(branches=False):
    action = {"entity": "paul", "category": "insurance.life", "subcategory": None}
    cond = [{"field": "counterparty", "op": "equals", "value": "Prévia Assurances"}]
    rule = ({"kind": "always", "discriminator": None, "branches": [{"conditions": cond, "action": action}]}
            if branches else {"kind": "always", "discriminator": None, "conditions": cond, "action": action})
    ask = ({"kind": "ask", "discriminator": None, "branches": []} if branches else
           {"kind": "ask", "discriminator": None, "conditions": [],
            "action": {"entity": None, "category": None, "subcategory": None}})
    return {"questions": [{
        "id": "q1", "text": "Is this contract personal?",
        "evidence": [{"doc_id": "d2", "quote": "Assuré : M. Paul Morel"},
                     {"doc_id": "d2", "quote": "Assuré : Paul Morel junior"}],
        "affected_doc_ids": ["d2"], "impact": "medium",
        "options": [{"id": "a", "label": "Personal", "rule_draft": rule},
                    {"id": "b", "label": "Ask me", "rule_draft": ask}],
        "suggested_option_id": "a"}]}


@pytest.mark.parametrize("branches", [False, True])
def test_valid_card_passes_schema_and_checks(branches):
    obj = card(branches)
    jsonschema.validate(obj, question_schema(CLUSTER, branches))
    c = check(obj, CLUSTER)
    assert c["evidence_quotes_verified"] == "1/2"
    assert c["suggested_in_options"] and c["docs_covered"] == ["d2"]


@pytest.mark.parametrize("mutate", [
    lambda o: o["questions"][0]["affected_doc_ids"].append("d99"),
    lambda o: o["questions"][0]["options"].pop(),
    lambda o: o["questions"].extend(copy.deepcopy(o["questions"]) * 7),
    lambda o: o["questions"][0]["options"][0]["rule_draft"]["action"].update(entity="unknown"),
])
def test_schema_rejects(mutate):
    obj = card()
    mutate(obj)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(obj, question_schema(CLUSTER))


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))

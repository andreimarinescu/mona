import re
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import pytest
import templates
import yaml

DEMO = Path(__file__).resolve().parents[1]
DOCS = yaml.safe_load((DEMO / "synthetic" / "docs.yaml").read_text(encoding="utf-8"))
SYN = {d["id"]: d for d in DOCS["docs"]}
ANCHOR = date.fromisoformat(
    DOCS["reference_anchor"].isoformat() if hasattr(DOCS["reference_anchor"], "isoformat") else DOCS["reference_anchor"]
)
SCRIPT_ORDER = [
    "945a8bd4c054",
    "syn-sie-letter",
    "79e0ba30cd98",
    "162ae8e85e14",
    "90f3898a7337",
    "d6759080655c",
    "syn-oxyleo-prep",
    "83ef9c3e34b2",
    "437dfdbb789d",
    "syn-supplier-rotated",
    "110c37b2aaa1",
    "86c269dd3165",
    "syn-agipi-per",
    "d4e32792cb51",
    "03f336dd6ee3",
    "051809a11573",
    "2fa37b7d01cf",
    "syn-unreadable",
    "syn-duplicate-urssaf",
]
PREFILED_SCRIPT = [
    *["2a7f59091e07", "3bb97ca05844", "bc1aa08e13ec", "804e66355f40", "18bd5e19bab9", "a0315e754e52"],
    *["b9c89da3fa92", "56d901f94557", "749383ec4112", "85f83829b38d", "70bb174428a1", "0a1de5b3b9d0"],
    *["e1574a7af51f", "a5a2e4a2b529", "syn-urssaf-call"],
]
ID = re.compile(r"^([0-9a-f]{12}|syn-[a-z0-9-]+)$")
REQUIRED_CASES = {
    "feedback-agipi",
    "feedback-hello-bank",
    "feedback-talenz",
    "feedback-oxyleo",
    "feedback-opco",
    "feedback-unim",
    "same-insurer-two-persons",
    "fy-crossing",
    "rotated-scan",
    "duplicate",
}


def final(entry: dict) -> dict:
    return entry["after"] if isinstance(entry["after"], dict) else entry["before"]


def state(entry: dict, tier: str) -> dict:
    return entry[tier] if isinstance(entry[tier], dict) else entry["before"]


def syn_dates(doc_id: str) -> dict:
    out = {}
    for key, spec in SYN[doc_id].get("dates", {}).items():
        if "offset" in spec:
            out[key] = ANCHOR + timedelta(days=spec["offset"])
        else:
            dy, month, day = spec["ym"]
            out[key] = date(ANCHOR.year + dy, month, day)
    return out


def doc_for(entry: dict, tier: str, values: dict, mime: str = "application/pdf") -> templates.Doc:
    s = state(entry, tier)
    return templates.Doc(
        entity=s["entity"],
        unit=s.get("unit"),
        category=s["category"],
        subcategory=s.get("subcategory"),
        counterparty=s.get("counterparty"),
        issuer=s.get("issuer"),
        reference=values.get("reference"),
        doc_date=values.get("doc_date"),
        period_end=values.get("period_end"),
        arrived_on=ANCHOR,
        mime_type=mime,
    )


def synthetic_values(doc_id: str) -> dict:
    dates = syn_dates(doc_id)
    return {
        "doc_date": dates.get("doc"),
        "period_end": dates.get("period_end"),
        "reference": SYN[doc_id].get("reference"),
    }


def has_destination(s: dict) -> bool:
    return "path" in s


def test_anchor_matches_the_generator_anchor(expectations):
    assert str(expectations["anchor"]) == str(DOCS["reference_anchor"]) == "2026-10-20"


def test_ids_are_unique_and_well_formed(expectations):
    ids = [e["id"] for e in expectations["docs"]]
    assert len(ids) == len(set(ids)) and all(ID.match(i) for i in ids)
    assert {i for i in ids if i.startswith("syn-")} == set(SYN)


def test_live_batch_is_the_demo_script_order(expectations):
    live = sorted((e for e in expectations["docs"] if e["group"] == "live"), key=lambda e: e["position"])
    assert [e["id"] for e in live] == SCRIPT_ORDER and [e["position"] for e in live] == list(range(1, 20))
    prefiled = [e["id"] for e in expectations["docs"] if e["group"] == "prefiled"]
    assert sorted(prefiled) == sorted(PREFILED_SCRIPT)


def test_acceptance_cases_are_all_covered(expectations):
    assert REQUIRED_CASES <= {c for e in expectations["docs"] for c in e.get("cases", [])}


def test_live_batch_tallies_match_the_script_before_and_after(expectations):
    live = [e for e in expectations["docs"] if e["group"] == "live"]
    before = Counter(state(e, "before")["outcome"] for e in live)
    assert before == {"file": 10, "queue": 7, "unreadable": 1, "duplicate": 1}
    after = Counter(final(e)["outcome"] for e in live)
    assert after == {"file": 16, "queue": 1, "unreadable": 1, "duplicate": 1}


def test_learned_rules_change_exactly_the_debrief_documents(expectations):
    changed = {e["id"] for e in expectations["docs"] if isinstance(e["after"], dict)}
    assert changed == {
        "110c37b2aaa1",
        "86c269dd3165",
        "syn-agipi-per",
        "d4e32792cb51",
        "03f336dd6ee3",
        "051809a11573",
        "syn-hello-fy-crossing",
    }
    for e in expectations["docs"]:
        if e["id"] in changed:
            assert (e["before"]["outcome"], e["before"]["reasons"]) == ("queue", ["entity"])
            assert e["after"]["outcome"] == "file" and e["after"]["rule"] in {
                "agipi-per-by-person",
                "agipi-assurance-vie-by-person",
                "hello-bank-lmnp",
            }


def test_references_resolve_and_rules_belong_to_their_tier(expectations, practice):
    seeded = {r["key"]: r for r in templates.load_rules()["rules"]}
    learned = {r["key"]: r for r in templates.load_rules("rules.learned.yaml")["rules"]}
    entities = {e["key"]: e for e in practice["entities"]}
    categories = {c["id"]: c for c in practice["categories"]}
    cps = {c["key"]: c["name"] for c in practice["counterparties"]}
    for e in expectations["docs"]:
        for tier in ("before", "after"):
            s = state(e, tier)
            if "rule" in s:
                assert s["rule"] in (seeded if tier == "before" else {**seeded, **learned}), (e["id"], tier)
            if "entity" in s:
                assert s["entity"] in entities
                units = {u["key"] for u in entities[s["entity"]].get("sub_units", [])}
                assert s.get("unit") is None or s["unit"] in units
                assert s["category"] in categories
                assert s.get("subcategory") is None or s["subcategory"] in {
                    x["key"] for x in categories[s["category"]]["subcategories"]
                }
            if "counterparty_key" in s:
                assert cps[s["counterparty_key"]] == s["counterparty"]


def test_rule_expectations_agree_with_the_rule_actions(expectations):
    rules = {r["key"]: r for r in templates.load_rules()["rules"] + templates.load_rules("rules.learned.yaml")["rules"]}
    for e in expectations["docs"]:
        for tier in ("before", "after"):
            s = state(e, tier)
            if s["basis"] != "rule":
                continue
            action = rules[s["rule"]]["action"]
            assert s["entity"] == action["entity"] and s["category"] == action["category"]
            if action.get("unit") == {"from": "person"}:
                assert s["unit"]
            else:
                assert s.get("unit") == action.get("unit")
            if "subcategory" in action:
                assert s["subcategory"] == action["subcategory"]
            if action.get("counterparty") is None and s.get("counterparty_key"):
                conds = rules[s["rule"]]["conditions"]
                named = [c["value"] for c in conds if c["field"] == "counterparty" and c["op"] == "equals"]
                assert not named or s["counterparty_key"] in named


def test_scores_follow_c5_9(expectations):
    high, low = expectations["thresholds"]["high"], expectations["thresholds"]["low"]
    reg = templates.Registry.from_practice(templates.load_practice(None))
    for e in expectations["docs"]:
        if e["source"] != "synthetic":
            continue
        for tier in ("before", "after"):
            s = state(e, tier)
            if s["basis"] == "rule":
                penalty = templates.render(reg, doc_for(e, tier, synthetic_values(e["id"]))).penalty
                assert s["confidence"] == 95 - penalty
                assert s["band"] == (
                    "high" if s["confidence"] >= high else "medium" if s["confidence"] >= low else "low"
                )
                assert (s["outcome"], s["reasons"]) == (("file", []) if s["band"] != "low" else ("queue", ["low"]))


def test_reasons_and_outcomes_are_consistent(expectations):
    for e in expectations["docs"]:
        for tier in ("before", "after"):
            s = state(e, tier)
            assert set(s["reasons"]) <= {"unreadable", "entity", "conflict", "low"}
            if s["outcome"] in {"file", "filed"}:
                assert not s["reasons"] and has_destination(s)
            if s["outcome"] == "queue":
                assert s["reasons"]
            if "entity" in s["reasons"]:
                assert not has_destination(s)
            if s["outcome"] == "unreadable":
                assert s["reasons"] == ["unreadable"]
            if s["outcome"] == "duplicate":
                assert s["reasons"] == [] and e["duplicate_of"] in SYN


@pytest.mark.parametrize("tier", ["before", "after"])
def test_synthetic_expectations_render(expectations, practice, tier):
    reg = templates.Registry.from_practice(practice)
    count = 0
    for e in (e for e in expectations["docs"] if e["source"] == "synthetic"):
        s = state(e, tier)
        if not has_destination(s):
            continue
        mime = "image/jpeg" if e["id"] == "syn-visitor-photo" else "application/pdf"
        out = templates.render(reg, doc_for(e, tier, synthetic_values(e["id"]), mime))
        assert (out.path, out.file_name, out.fiscal_year) == (s["path"], s["file_name"], s["fiscal_year"]), e["id"]
        count += 1
    assert count == {"before": 8, "after": 10}[tier]


def test_synthetic_docs_yaml_carries_the_final_destination(expectations):
    for e in expectations["docs"]:
        if e["source"] != "synthetic" or "expected" not in SYN[e["id"]] or "path" not in SYN[e["id"]]["expected"]:
            continue
        s, x = final(e), SYN[e["id"]]["expected"]
        assert (x["path"], x["file_name"], x["fiscal_year"]) == (s["path"], s["file_name"], s["fiscal_year"]), e["id"]
        assert (x["entity"], x.get("sub_unit"), x["category"], x.get("subcategory")) == (
            s["entity"],
            s.get("unit"),
            s["category"],
            s.get("subcategory"),
        )


def test_real_expectations_render_with_private_values(expectations, private_practice, private_expectations):
    reg = templates.Registry.from_practice(private_practice)
    pub = templates.Registry.from_practice(templates.load_practice(None))
    checked = 0
    for e in (e for e in expectations["docs"] if e["source"] == "corpus"):
        priv = private_expectations[e["id"]]
        values = {k: date.fromisoformat(v) if k in {"doc_date", "period_end"} else v for k, v in priv["values"].items()}
        for tier in ("before", "after"):
            s = state(e, tier)
            if not has_destination(s):
                continue
            want = priv[tier] if isinstance(priv[tier], dict) else priv["before"]
            out = templates.render(reg, doc_for(e, tier, values))
            assert (out.path, out.file_name, out.penalty) == (want["path"], want["file_name"], want["penalty"]), (
                e["id"],
                tier,
            )
            assert out.fiscal_year == s["fiscal_year"], (e["id"], tier)
            assert templates.render(pub, doc_for(e, tier, values)).path == s["path"], (e["id"], tier)
            if s["basis"] == "rule":
                assert s["confidence"] == 95 - out.penalty, (e["id"], tier)
            checked += 1
    assert checked == 49

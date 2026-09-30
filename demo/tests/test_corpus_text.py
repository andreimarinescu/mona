import functools
import json
import re
import subprocess
from pathlib import Path

import pytest
import templates
import textnorm
import yaml
from conftest import PRIVATE_DIR

HQ = PRIVATE_DIR.parents[1]
MANIFEST = PRIVATE_DIR.parent / "corpus" / "manifest.jsonl"
PDFS = HQ / "100 PDF neclasificate"
CACHE = HQ / "bench" / "corpus" / "textcache"
RULES = {r["key"]: r for r in templates.load_rules()["rules"] + templates.load_rules("rules.learned.yaml")["rules"]}

pytestmark = pytest.mark.skipif(not (MANIFEST.exists() and PDFS.is_dir()), reason="private corpus not available")


@functools.cache
def rows() -> dict:
    return {r["id"]: r for r in map(json.loads, MANIFEST.read_text(encoding="utf-8").splitlines())}


@functools.cache
def haystack(doc_id: str) -> str:
    row = rows()[doc_id]
    if row["valid_pdf"]:
        text = subprocess.run(
            ["pdftotext", "-layout", "-enc", "UTF-8", str(PDFS / row["filename"]), "-"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout
        if len(re.sub(r"\s", "", text)) >= 50:
            return textnorm.norm(text)
    cached = CACHE / (row["filename"] + ".txt")
    return textnorm.norm(cached.read_text(encoding="utf-8", errors="replace")) if cached.exists() else ""


def text_holds(rule: dict, doc_id: str) -> bool:
    hay = haystack(doc_id)
    for cond in (c for c in rule["conditions"] if c["field"] == "text"):
        needles = [textnorm.norm(v) for v in (cond["value"] if isinstance(cond["value"], list) else [cond["value"]])]
        hits = [textnorm.whole_word(n, hay) for n in needles]
        holds = all(hits) if cond["op"] == "contains_all" else any(hits)
        if holds == bool(cond.get("negate")):
            return False
    return True


def lmnp_ibans(overlay: dict) -> list[str]:
    return [re.sub(r"[^0-9A-Z]", "", v["iban"].upper()) for k, v in overlay["accounts"].items() if k == "lmnp-hello"]


def holds_iban(overlay: dict, doc_id: str) -> bool:
    flat = re.sub(r"[^0-9A-Z]", "", haystack(doc_id).upper())
    return any(i in flat for i in lmnp_ibans(overlay))


def real_states(expectations):
    for e in (e for e in expectations["docs"] if e["source"] == "corpus"):
        for tier in ("before", "after"):
            s = e[tier] if isinstance(e[tier], dict) else e["before"]
            if s["basis"] == "rule":
                yield e["id"], tier, s["rule"]


def test_every_expected_rule_matches_the_document_text(expectations, overlay):
    if overlay is None:
        pytest.skip("private overlay not available")
    seen = 0
    for doc_id, tier, key in real_states(expectations):
        assert text_holds(RULES[key], doc_id), (doc_id, tier, key)
        if any(c["field"] == "iban" for c in RULES[key]["conditions"]):
            assert holds_iban(overlay, doc_id), (doc_id, tier, key)
        seen += 1
    assert seen >= 25


def test_text_only_rules_fire_on_exactly_the_expected_documents(expectations):
    stubs = {i for i, r in rows().items() if not r["valid_pdf"]}
    for key in ("selarl-annual-accounts", "payroll-selarl"):
        expected = {i for i, _, k in real_states(expectations) if k == key}
        fired = {i for i in rows() if text_holds(RULES[key], i)}
        assert expected and fired - stubs == expected, key


def test_iban_rule_fires_on_exactly_the_hello_statements(expectations, overlay):
    if overlay is None:
        pytest.skip("private overlay not available")
    labelled = {e["id"] for e in expectations["docs"] if e["source"] == "corpus" and "Hello bank" in e["label"]}
    stubs = {i for i, r in rows().items() if not r["valid_pdf"]}
    holding = {i for i in rows() if holds_iban(overlay, i)}
    assert labelled and holding - stubs == labelled


def test_per_and_life_rules_never_both_match_a_document():
    per, life = RULES["agipi-per-by-person"], RULES["agipi-assurance-vie-by-person"]
    both = [i for i in rows() if text_holds(per, i) and text_holds(life, i)]
    assert both == []
    assert any(text_holds(per, i) for i in rows()) and any(text_holds(life, i) for i in rows())


def test_overlay_yaml_loads_as_the_seed_expects(overlay):
    if overlay is None:
        pytest.skip("private overlay not available")
    assert set(overlay) >= {"people", "entities", "counterparties", "accounts"}
    assert yaml.safe_load(Path(templates.overlay_path()).read_text(encoding="utf-8"))

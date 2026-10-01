"""L5's demo/expectations.yaml diffed against this renderer (private values only when present)."""

import os
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml

from mona.templates import EntityInfo, RenderValues, render

REPO = Path(__file__).resolve().parents[3]
DEMO = REPO / "demo"
PRIVATE = Path(
    os.environ.get(
        "MONA_SEED_OVERLAY", Path.home() / "DevFiles/mona-hq/demo-data/seed/identifiers.yaml"
    )
).parent


def _yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _resolve(node: Any, overlay: dict | None) -> Any:
    if isinstance(node, dict):
        if set(node) == {"ref"}:
            if overlay is None:
                return None
            value: Any = overlay
            for part in node["ref"].split("."):
                value = value[part]
            return value
        return {k: _resolve(v, overlay) for k, v in node.items()}
    if isinstance(node, list):
        return [_resolve(v, overlay) for v in node]
    return node


class Practice:
    def __init__(self, raw: dict):
        self.language = raw["practice"]["filing_language"]
        self.entities = {e["key"]: e for e in raw["entities"]}
        self.categories = {c["id"]: c for c in raw["categories"]}
        self.templates = {(t["category"], t.get("entity")): t for t in raw["templates"]}

    def render(self, s: dict, v: dict, anchor: date, mime: str):
        e = self.entities[s["entity"]]
        cat = self.categories[s["category"]]
        sub = next((x for x in cat["subcategories"] if x["key"] == s.get("subcategory")), None)
        unit = next((u for u in e.get("sub_units", []) if u["key"] == s.get("unit")), None)
        key = (s["category"], s["entity"])
        tpl = self.templates.get(key) or self.templates[(s["category"], None)]
        values = RenderValues(
            entity=EntityInfo(
                e["key"],
                e["folder_name"],
                e["fy_end_month"],
                e["fy_end_day"],
                e.get("filing_language"),
            ),
            arrived_at=anchor,
            language=self.language,
            sub_unit_label=unit["label"] if unit else None,
            category_labels=cat["labels"],
            subcategory_labels=sub["labels"] if sub else None,
            counterparty=s.get("counterparty"),
            issuer=s.get("issuer"),
            reference=v.get("reference"),
            doc_date=v.get("doc_date"),
            period_end=v.get("period_end"),
            mime_type=mime,
        )
        return render(tpl["path_template"], tpl["file_template"], values)


EXPECTATIONS = _yaml(DEMO / "expectations.yaml")
ANCHOR = date.fromisoformat(str(EXPECTATIONS["anchor"]))
SYNTHETIC = {d["id"]: d for d in _yaml(DEMO / "synthetic" / "docs.yaml")["docs"]}


def _state(entry: dict, tier: str) -> dict:
    return entry[tier] if isinstance(entry[tier], dict) else entry["before"]


def _synthetic_values(doc: dict) -> dict:
    out: dict[str, Any] = {"reference": doc.get("reference")}
    for key, spec in doc.get("dates", {}).items():
        if "offset" in spec:
            d = ANCHOR + timedelta(days=spec["offset"])
        else:
            dy, month, day = spec["ym"]
            d = date(ANCHOR.year + dy, month, day)
        out[{"doc": "doc_date"}.get(key, key)] = d
    return out


def _mime(doc_id: str) -> str:
    return "image/jpeg" if doc_id == "syn-visitor-photo" else "application/pdf"


@pytest.mark.parametrize("tier", ["before", "after"])
def test_synthetic_expectations_match_the_renderer(tier):
    practice = Practice(_resolve(_yaml(DEMO / "seed" / "practice.yaml"), None))
    checked = []
    for e in EXPECTATIONS["docs"]:
        s = _state(e, tier)
        if e["source"] != "synthetic" or "path" not in s:
            continue
        out = practice.render(s, _synthetic_values(SYNTHETIC[e["id"]]), ANCHOR, _mime(e["id"]))
        got = (out.folder, out.file_name, out.fiscal_year)
        assert got == (s["path"], s["file_name"], s["fiscal_year"]), e["id"]
        if s.get("basis") == "rule":
            assert s["confidence"] == 95 - out.penalty, e["id"]
        checked.append(e["id"])
    assert len(checked) == {"before": 10, "after": 12}[tier]


@pytest.mark.skipif(
    not (PRIVATE / "expectations.private.yaml").exists(), reason="private expectations absent"
)
def test_private_expectations_match_the_renderer():
    """Reports mismatching ids only, so no private value reaches the output."""
    practice = Practice(
        _resolve(_yaml(DEMO / "seed" / "practice.yaml"), _yaml(PRIVATE / "identifiers.yaml"))
    )
    private = _yaml(PRIVATE / "expectations.private.yaml")
    mismatched, checked = [], 0
    for e in (e for e in EXPECTATIONS["docs"] if e["source"] == "corpus"):
        priv = private[e["id"]]
        v = {
            k: date.fromisoformat(x) if k in {"doc_date", "period_end"} and x else x
            for k, x in priv["values"].items()
        }
        for tier in ("before", "after"):
            s = _state(e, tier)
            if "path" not in s:
                continue
            want = priv[tier] if isinstance(priv[tier], dict) else priv["before"]
            out = practice.render(s, v, ANCHOR, "application/pdf")
            got = (out.folder, out.file_name, out.penalty, out.fiscal_year)
            if got != (want["path"], want["file_name"], want["penalty"], s["fiscal_year"]):
                mismatched.append((e["id"], tier))
            checked += 1
    assert mismatched == []
    assert checked == 49

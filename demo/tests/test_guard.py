import re
import subprocess
from pathlib import Path

import pytest
import templates
import yaml

ROOT = Path(__file__).resolve().parents[2]
PATTERNS = {
    "IBAN": re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){2,7}(?:[ ]?[A-Z0-9]{1,4})?\b"),
    "SIREN": re.compile(r"(?<!\d)\d{3}[ .]?\d{3}[ .]?\d{3}(?!\d)"),
    "SIRET": re.compile(r"(?<!\d)\d{14}(?!\d)"),
}
OWNER_TOKENS = {"claudiu", "gamulescu", "christine", "simina", "dr"}


def tracked_text_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    paths = [ROOT / p for p in out.split("\0") if p]
    return [
        p
        for p in paths
        if p.suffix in {".py", ".yaml", ".yml", ".md", ".json", ".toml", ".ts", ".tsx", ".txt"} and p.exists()
    ]


def untracked_demo_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "-z", "--others", "--exclude-standard", "demo"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [ROOT / p for p in out.split("\0") if p and "__pycache__" not in p]


def demo_files() -> list[Path]:
    return [p for p in {*tracked_text_files(), *untracked_demo_files()} if "demo" in p.relative_to(ROOT).parts[:1]]


def leaves(node):
    if isinstance(node, dict):
        for v in node.values():
            yield from leaves(v)
    elif isinstance(node, list):
        for v in node:
            yield from leaves(v)
    elif isinstance(node, str):
        yield node


def _owner_only(value: str) -> bool:
    return {t.lower() for t in re.findall(r"[^\W\d_]+", value)} <= OWNER_TOKENS


GENERATED = Path.home() / "DevFiles/mona-hq/demo-data/synthetic/generated-identifiers.yaml"


def private_needles(overlay: dict) -> set[str]:
    """Identifiers only (D1: names may be committed); the generator's fictional values are not private."""
    fictional = set(leaves(yaml.safe_load(GENERATED.read_text()))) if GENERATED.exists() else set()
    identifiers = {k: v for k, v in overlay.items() if k != "people"}
    return {v.strip() for v in leaves(identifiers) if len(v.strip()) >= 4 and not _owner_only(v) and v not in fictional}


@pytest.mark.parametrize("name", sorted(PATTERNS))
def test_no_identifier_patterns_in_demo_files(name):
    files = demo_files()
    assert len(files) > 10
    for path in files:
        if path.suffix not in {".py", ".yaml", ".md"}:
            continue
        text = path.read_text(encoding="utf-8")
        assert not PATTERNS[name].search(text), f"{path.relative_to(ROOT)} matches the {name} pattern"


def test_no_private_values_in_any_tracked_file(overlay):
    if overlay is None:
        pytest.skip("private overlay not available")
    needles = private_needles(overlay)
    assert len(needles) >= 3
    files = list({*tracked_text_files(), *untracked_demo_files()})
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        for needle in needles:
            if needle.lower() in text.lower():
                pytest.fail(f"{path.relative_to(ROOT)} contains a private value from the overlay")


def test_committed_seed_carries_references_not_values():
    raw = yaml.safe_load((ROOT / "demo" / "seed" / "practice.yaml").read_text(encoding="utf-8"))
    for account in raw["accounts"]:
        assert set(account["iban"]) == {"ref"}
    for entity in raw["entities"]:
        for key in ("siren", "addresses"):
            assert key not in entity or set(entity[key]) == {"ref"}
    assert all(set(p["display_name"]) == {"ref"} for p in raw["people"] if p["key"].startswith("child-"))


def test_guard_catches_a_planted_identifier():
    planted = "FR" + "76" + " 1111" * 5 + " 111"
    assert PATTERNS["IBAN"].search(planted)
    assert PATTERNS["SIREN"].search("123" + " 456" + " 789") and PATTERNS["SIRET"].search("1" * 14)
    assert templates.resolve_refs({"ref": "people.child-1.short_name"}, None) == "@child-1"

"""D12: the guard `scripts/no-practice-names.py` over the repo and over planted names."""

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
GUARD = ROOT / "scripts" / "no-practice-names.py"


def run(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GUARD), "--root", str(root)], capture_output=True, text=True
    )


@pytest.fixture
def tree(tmp_path):
    (tmp_path / "demo" / "seed").mkdir(parents=True)
    shutil.copy(ROOT / "demo" / "seed" / "practice.yaml", tmp_path / "demo" / "seed")
    for d in (
        "apps/api/src/mona",
        "apps/api/tests/fixtures/hermes",
        "apps/api/tests/fixtures/pipeline",
        "apps/web/src/chat",
        "apps/web/src/mocks",
        "packages/ui/src",
        "deploy/hermes/memories",
    ):
        (tmp_path / d).mkdir(parents=True)
    (tmp_path / "apps/api/src/mona/tool.py").write_text('HINT = "a supplier or a bank"\n')
    return tmp_path


def test_the_repo_has_no_practice_names():
    res = run(ROOT)
    assert res.returncode == 0, res.stdout + res.stderr


def test_a_clean_tree_passes(tree):
    assert run(tree).returncode == 0


@pytest.mark.parametrize(
    ("path", "line"),
    [
        ("apps/api/src/mona/tool.py", 'HINT = "e.g. hello BANK statements"'),
        ("apps/web/src/chat/Hint.tsx", "const x = 'Ask TALENZ';"),
        ("packages/ui/src/label.ts", "export const who = 'claudiu';"),
        ("deploy/hermes/SOUL.md", "- Filed under SCI C Immobilier."),
        ("apps/web/src/mocks/seed.ts", "  { displayName: 'Hello bank' },"),
        ("apps/api/tests/fixtures/hermes/surface.json", '{"description": "e.g. a UNIM notice"}'),
        ("apps/api/tests/fixtures/pipeline/other.json", '{"issuer": "OXYLEO"}'),
    ],
)
def test_a_planted_name_fails_the_guard(tree, path, line):
    (tree / path).write_text(line + "\n")
    res = run(tree)
    assert res.returncode == 1
    assert res.stdout.startswith(f"{path}:1: ")


@pytest.mark.parametrize(
    ("path", "line"),
    [
        ("deploy/hermes/memories/MEMORY.md", "The accountant is TALENZ."),
        ("apps/web/src/chat/stream.test.ts", "label: 'AGIPI'"),
        ("apps/web/src/chat/fixtures/live.sse", "Claudiu prefers"),
        ("apps/api/src/mona/tool.py", "MAESTRO = 'Visitors purge, URSSAF call'"),
        ("docs/notes.md", "AGIPI"),
        ("apps/api/tests/fixtures/pipeline/demo-overlay.yaml", "agipi: AGIPI"),
        ("apps/api/tests/fixtures/pipeline/synthetic.json", '{"issuer": "TALENZ"}'),
        ("apps/api/tests/fixtures/pipeline/model_outputs.json", '{"issuer": "UNIM"}'),
        ("apps/api/tests/fixtures/seed/practice.yaml", "name: AGIPI"),
        ("apps/api/tests/fixtures/interviews/cluster.json", '{"title": "Hello bank"}'),
        ("apps/api/tests/fixtures/hermes/surface.json", '{"description": "Visitors purge"}'),
    ],
)
def test_examples_tests_generated_memory_and_generic_names_pass(tree, path, line):
    (tree / path).parent.mkdir(parents=True, exist_ok=True)
    (tree / path).write_text(line + "\n")
    assert run(tree).returncode == 0


def test_the_web_mocks_name_no_entity_of_the_seed():
    seed = yaml.safe_load((ROOT / "demo" / "seed" / "practice.yaml").read_text(encoding="utf-8"))
    names = {e["folder_name"] for e in seed["entities"]} - {"Visitors"}
    pattern = re.compile(r"(?<!\w)(" + "|".join(map(re.escape, names)) + r")(?!\w)")
    hits = [
        f"{p.relative_to(ROOT)}: {m.group(0)}"
        for d in ("apps/web/src/mocks", "apps/web/src/test")
        for p in sorted((ROOT / d).rglob("*.ts*"))
        for m in pattern.finditer(p.read_text(encoding="utf-8"))
    ]
    assert hits == []

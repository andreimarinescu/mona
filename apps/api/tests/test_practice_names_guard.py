"""D12: the guard `scripts/no-practice-names.py` over the repo and over planted names."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

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
        "apps/web/src/chat",
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
    ],
)
def test_examples_tests_generated_memory_and_generic_names_pass(tree, path, line):
    (tree / path).parent.mkdir(parents=True, exist_ok=True)
    (tree / path).write_text(line + "\n")
    assert run(tree).returncode == 0

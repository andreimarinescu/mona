import sys
from pathlib import Path

import pytest
import yaml

DEMO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DEMO / "scripts"))

import templates  # noqa: E402

PRIVATE_DIR = templates.overlay_path().parent


@pytest.fixture(scope="session")
def overlay():
    return templates.load_overlay()


@pytest.fixture(scope="session")
def practice():
    return templates.load_practice(None)


@pytest.fixture(scope="session")
def private_practice(overlay):
    if overlay is None:
        pytest.skip("private overlay not available")
    return templates.load_practice(overlay)


@pytest.fixture(scope="session")
def expectations():
    return yaml.safe_load((DEMO / "expectations.yaml").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def private_expectations():
    path = PRIVATE_DIR / "expectations.private.yaml"
    if not path.exists():
        pytest.skip("private expectations not available")
    return yaml.safe_load(path.read_text(encoding="utf-8"))

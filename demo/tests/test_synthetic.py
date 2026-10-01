import hashlib
import json
import re
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml
from PIL import Image

DEMO = Path(__file__).resolve().parents[1]
GENERATOR = DEMO / "synthetic" / "generate.py"
DOCS = yaml.safe_load((DEMO / "synthetic" / "docs.yaml").read_text(encoding="utf-8"))["docs"]
ANCHOR = "2026-10-20"


@pytest.fixture(scope="module")
def rendered(tmp_path_factory):
    out = tmp_path_factory.mktemp("synthetic")
    proc = subprocess.run(
        [sys.executable, str(GENERATOR), "--anchor", ANCHOR, "--out", str(out)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip().endswith(f"{len(DOCS)} documents, 0 errors")
    return out, json.loads((out / "manifest.json").read_text(encoding="utf-8"))["docs"]


def norm(text: str) -> str:
    return re.sub(r"[\s  ]+", " ", text)


def pdf_text(path: Path) -> str:
    return norm(
        subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True, check=False).stdout
    )


def fr_date(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%d/%m/%Y")


def fr_amount(value: float) -> str:
    whole, cents = f"{value:.2f}".split(".")
    return f"{int(whole):,}".replace(",", " ") + "," + cents


TEXT_DOCS = [d for d in DOCS if d["render"] == "pdf"]


def test_every_document_is_rendered(rendered):
    out, manifest = rendered
    assert set(manifest) == {d["id"] for d in DOCS}
    for info in manifest.values():
        assert (out / info["file"]).stat().st_size > 0


@pytest.mark.parametrize("doc", TEXT_DOCS, ids=lambda d: d["id"])
def test_text_layer_holds_the_key_fields(rendered, doc):
    out, manifest = rendered
    info = manifest[doc["id"]]
    text = pdf_text(out / info["file"])
    assert fr_date(info["dates"]["doc"]) in text
    if "due" in info["dates"]:
        assert fr_date(info["dates"]["due"]) in text
    if "amount" in doc:
        assert fr_amount(doc["amount"]["value"]) in text


@pytest.mark.parametrize("doc", [d for d in TEXT_DOCS if "amount" in d], ids=lambda d: d["id"])
def test_the_amount_never_wraps_across_lines(rendered, doc):
    out, manifest = rendered
    layout = subprocess.run(
        ["pdftotext", "-layout", str(out / manifest[doc["id"]]["file"]), "-"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    assert any(fr_amount(doc["amount"]["value"]) in norm(line) for line in layout.splitlines())


def test_bank_statement_balances_and_crosses_the_year_end(rendered):
    _, manifest = rendered
    doc = next(d for d in DOCS if d["template"] == "statement")
    closing = round(doc["opening_balance"] + sum(r["amount"] for r in doc["rows"]), 2)
    assert closing == doc["amount"]["value"]
    dates = manifest[doc["id"]]["dates"]
    assert date.fromisoformat(dates["period_start"]).year + 1 == date.fromisoformat(dates["period_end"]).year


def test_urssaf_demand_is_due_within_seven_days_of_the_anchor(rendered):
    _, manifest = rendered
    due = date.fromisoformat(manifest["syn-urssaf-call"]["dates"]["due"])
    assert timedelta(0) < due - date.fromisoformat(ANCHOR) <= timedelta(days=7)


def test_scans_are_image_only_and_rotated(rendered):
    out, manifest = rendered
    scan = out / manifest["syn-supplier-rotated"]["file"]
    assert len(pdf_text(scan)) < 50
    info = subprocess.run(
        ["pdfinfo", "-f", "1", "-l", "2", str(scan)], capture_output=True, text=True, check=False
    ).stdout
    assert re.search(r"^Pages:\s+2", info, re.MULTILINE)
    sizes = [(float(w), float(h)) for w, h in re.findall(r"size:\s+([\d.]+) x ([\d.]+)", info)]
    assert sizes[0][0] > sizes[0][1] and sizes[1][0] < sizes[1][1]
    unreadable = out / manifest["syn-unreadable"]["file"]
    assert len(pdf_text(unreadable)) < 50


def test_photo_is_a_jpeg_with_perspective_canvas(rendered):
    out, manifest = rendered
    with Image.open(out / manifest["syn-visitor-photo"]["file"]) as img:
        assert img.format == "JPEG" and img.size == (1600, 1200)


def test_duplicate_is_byte_identical_under_another_name(rendered):
    out, manifest = rendered
    dup, orig = manifest["syn-duplicate-urssaf"], manifest["syn-urssaf-call"]
    assert dup["file"] != orig["file"] and dup["sha256"] == orig["sha256"]
    assert hashlib.sha256((out / dup["file"]).read_bytes()).hexdigest() == orig["sha256"]


def test_generator_refuses_to_write_inside_the_repo():
    proc = subprocess.run(
        [sys.executable, str(GENERATOR), "--anchor", ANCHOR, "--out", str(DEMO / "synthetic" / "out")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 2

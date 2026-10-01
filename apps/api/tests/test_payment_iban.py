"""A30: `payment_iban` is deterministic, verified, exposed, masked on Telegram and backfilled."""

import hashlib
from datetime import date, timedelta

import pytest

from mona import clock
from mona.iban import iban_hash
from mona.pipeline import cache
from mona.pipeline.intake import Upload, ingest_files
from mona.pipeline.payment_iban import backfill, find, mask
from mona.services.registry import T
from tests import rows
from tests.mcp_http import call
from tests.pipeline_world import RECORDED, SYNTHETIC, Pipeline, mini_pdf

PRACTICE = "FR76 3000 6000 0112 3456 7890 189"
SUPPLIER = "FR76 9999 9000 0101 2345 6789 012"
SUPPLIER_NORM = "FR7699999000010123456789012"
BAD_CHECKSUM = "FR76 9999 9000 0101 2345 6789 013"
SALT = b"s" * 32


def test_the_practice_account_is_skipped_and_the_payee_wins():
    pages = [f"Prélevé sur votre compte {PRACTICE}", f"Payer à IBAN : {SUPPLIER}"]
    found = find(pages, {iban_hash(PRACTICE, SALT)}, SALT)
    assert found is not None
    assert (found.value, found.page, found.quote) == (SUPPLIER_NORM, 2, SUPPLIER)
    assert found.find_query == SUPPLIER


def test_a_bad_checksum_is_ignored_and_no_candidate_is_none():
    assert find([f"IBAN {BAD_CHECKSUM}"], set(), SALT) is None
    assert find(["Facture sans coordonnées bancaires"], set(), SALT) is None
    assert find([f"IBAN {BAD_CHECKSUM}\nou {SUPPLIER}"], set(), SALT).value == SUPPLIER_NORM


def test_the_first_candidate_in_page_order_keeps_its_printed_case():
    found = find([f"iban {SUPPLIER.lower()}", "RO60 DEMO 0000 1234 5678 9012"], set(), SALT)
    assert found.value == SUPPLIER_NORM and found.quote == SUPPLIER.lower()


def test_telegram_mask_keeps_the_country_and_last_four():
    assert mask(SUPPLIER_NORM) == "FR •• 9012"
    assert mask(None) is None


# --- through classification (C5 §6, §7) ---


def _drop_invoice(p: Pipeline, extra: str) -> str:
    base = SYNTHETIC["syn-supplier-rotated"]
    pages = (base["pages"][0] + extra, *base["pages"][1:])
    content = mini_pdf(pages)
    sha = hashlib.sha256(content).hexdigest()
    cache.write_pages(p.ctx.textcache, cache.Pages(sha, "pdftotext", pages))
    p.cache_model(sha, RECORDED["outputs"]["syn-supplier-rotated"])
    intake = ingest_files(p.ctx, [Upload(content, "facture-iban.pdf")])
    p.drain()
    return intake.items[0].document_id


@pytest.fixture
def pipeline(l1m2_demo_engine, tmp_path) -> Pipeline:
    p = Pipeline(l1m2_demo_engine, tmp_path / "data")
    p.filed_history("Dentalis Fournitures")
    return p


def test_classification_stores_the_payee_iban_with_verified_evidence(pipeline):
    doc = _drop_invoice(pipeline, f"\nPrélèvement : {PRACTICE}\nIBAN : {SUPPLIER}\n")
    assert pipeline.row(doc)["payment_iban"] == SUPPLIER_NORM
    ext = pipeline.row(doc)["extraction_id"]
    [field] = pipeline.rows("extraction_fields", extraction_id=ext, key="payment_iban")
    assert (field["value"], field["quote"], field["page"], field["verified"]) == (
        SUPPLIER_NORM, SUPPLIER, 1, True,
    )  # fmt: skip
    assert field["find_query"] == SUPPLIER and field["confidence"] == 100


def test_only_the_practice_account_or_a_bad_checksum_leaves_it_null(pipeline):
    doc = _drop_invoice(pipeline, f"\nPrélèvement : {PRACTICE}\nIBAN : {BAD_CHECKSUM}\n")
    assert pipeline.row(doc)["payment_iban"] is None
    ext = pipeline.row(doc)["extraction_id"]
    assert pipeline.rows("extraction_fields", extraction_id=ext, key="payment_iban") == []


def test_backfill_fills_existing_documents_once(pipeline):
    doc = _drop_invoice(pipeline, f"\nIBAN : {SUPPLIER}\n")
    plain = _drop_invoice(pipeline, "\nRèglement par chèque.\n")
    ext = pipeline.row(doc)["extraction_id"]
    with pipeline.engine.begin() as conn:
        conn.execute(T["documents"].update().values(payment_iban=None))
        conn.execute(
            T["extraction_fields"].delete().where(T["extraction_fields"].c.key == "payment_iban")
        )
    first = backfill(pipeline.ctx)
    assert (first.checked, first.changed) == (2, 1)
    assert pipeline.row(doc)["payment_iban"] == SUPPLIER_NORM
    assert pipeline.row(plain)["payment_iban"] is None
    [field] = pipeline.rows("extraction_fields", extraction_id=ext, key="payment_iban")
    assert field["verified"] and field["quote"] == SUPPLIER
    again = backfill(pipeline.ctx)
    assert (again.checked, again.changed) == (2, 0)


# --- MCP results (C4 §3.1, §3.2, §3.10) ---


@pytest.fixture
def billed(clean) -> str:
    doc = rows.document(
        "Dentalis facture", entity="cabinet", category="payment_calls", amount=386.4,
        due_date=clock.paris_today() + timedelta(days=5), doc_date=date(2026, 9, 1),
    )  # fmt: skip
    with rows.connect() as conn:
        conn.execute("UPDATE documents SET payment_iban = %s WHERE id = %s", (SUPPLIER_NORM, doc))
    rows.deadline("Dentalis facture", clock.paris_today() + timedelta(days=5), document_id=doc)
    return doc


@pytest.mark.parametrize(("channel", "shown"), [("web", SUPPLIER_NORM), ("telegram", "FR •• 9012")])
async def test_tools_return_the_iban_and_telegram_masks_it(billed, channel, shown):
    got = await call("get_document", {"document_id": billed}, channel=channel)
    assert got.data["payment_iban"] == shown
    found = await call("search_documents", {"query": "Dentalis"}, channel=channel)
    assert [r["payment_iban"] for r in found.data["results"]] == [shown]
    due = await call("list_deadlines", {}, channel=channel)
    assert [i["payment_iban"] for i in due.data["items"]] == [shown]

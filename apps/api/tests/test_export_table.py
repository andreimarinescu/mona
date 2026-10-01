"""A31 `export_table`: CSV, XLSX and DOCX files, visibility, the 500-row cut, the formula guard."""

import csv
import io
import time
from datetime import date, datetime

import pytest
from docx import Document as DocxDocument
from openpyxl import load_workbook
from sqlalchemy import select

from mona.app import create_app
from mona.services.registry import T
from mona.workflow.common import get_ctx
from tests import rows
from tests.api_client import api_client
from tests.l4_world import World
from tests.mcp_http import call

pytestmark = pytest.mark.usefixtures("l4_db")

IBAN = "FR7699999000010123456789012"
ENTITY = "Cabinet Marchand SELARL"
INJECTIONS = ['=HYPERLINK("http://x","OPCO")', "+33 call", "-5 credit", "@SUM(A1)"]
COLUMNS = ["title", "entity", "due_date", "payment_iban", "amount"]


@pytest.fixture
async def api():
    async with api_client(create_app()) as c:
        yield c


@pytest.fixture
def payables() -> dict[str, str]:
    w = World()
    b = w.batch()
    d = {
        "opco": w.doc("OPCO contribution", batch=b, status="filed", reasons=[], entity="cabinet",
                      category="payment_calls", path="Cabinet Marchand/opco.pdf",
                      doc_date="2026-09-01", amount=1284.6, due_date=date(2026, 10, 15),
                      payment_iban=IBAN),
        "urssaf": w.doc("URSSAF call", batch=b, status="filed", reasons=[], entity="cabinet",
                        category="payment_calls", path="Cabinet Marchand/urssaf.pdf",
                        doc_date="2026-08-01", amount=412.0, due_date=date(2026, 10, 5)),
        "personal": w.doc("Personal tax", batch=b, status="filed", reasons=[], entity="personal",
                          category="payment_calls", path="Personnel/tax.pdf",
                          doc_date="2026-07-01", amount=900.0, due_date=date(2026, 11, 1),
                          payment_iban=IBAN),
    }  # fmt: skip
    return d


async def _file(api, export_id: str) -> tuple[dict, bytes]:
    pack = (await api.get(f"/api/exports/{export_id}")).json()
    res = await api.get(pack["fileUrl"])
    assert res.status_code == 200, res.text
    return pack, res.content


async def test_csv_holds_the_rows_and_columns_asked_for(api, payables):
    res = await call("export_table", {"category": "payment_calls", "columns": COLUMNS,
                                      "format": "csv", "title": "Payables"})  # fmt: skip
    assert not res.is_error, res.text
    assert (res.data["rows"], res.data["truncated"]) == (3, False)
    assert res.data["file_name"] == "Payables.csv"
    pack, raw = await _file(api, res.data["export_id"])
    assert (pack["format"], pack["title"], pack["entityId"], pack["fileName"]) == (
        "csv", "Payables", None, "Payables.csv",
    )  # fmt: skip
    table = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
    assert table[0] == COLUMNS
    assert table[1] == ["OPCO contribution", ENTITY, "2026-10-15", IBAN, "1284.60"]
    assert [r[0] for r in table[1:]] == ["OPCO contribution", "URSSAF call", "Personal tax"]


async def test_xlsx_has_typed_cells(api, payables):
    ids = [payables["urssaf"], payables["opco"]]
    res = await call("export_table", {"document_ids": ids, "columns": COLUMNS, "format": "xlsx",
                                      "lang": "fr"})  # fmt: skip
    assert not res.is_error, res.text
    _, raw = await _file(api, res.data["export_id"])
    ws = load_workbook(io.BytesIO(raw)).active
    values = list(ws.iter_rows(values_only=True))
    assert values[0] == ("Titre", "Entité", "Échéance", "IBAN de paiement", "Montant")
    assert values[1] == ("URSSAF call", ENTITY, datetime(2026, 10, 5), None, 412.0)
    assert values[2][3] == IBAN and values[2][4] == 1284.6
    assert ws["C2"].is_date and ws["E2"].data_type == "n" and ws["A2"].data_type == "s"


async def test_docx_is_a_titled_table_in_the_request_locale(api, payables):
    args = {"document_ids": [payables["opco"]], "columns": COLUMNS, "format": "docx"}
    res = await call("export_table", {**args, "title": "Échéances", "lang": "fr"})
    assert not res.is_error, res.text
    _, raw = await _file(api, res.data["export_id"])
    doc = DocxDocument(io.BytesIO(raw))
    assert doc.paragraphs[0].text == "Échéances" and doc.core_properties.title == "Échéances"
    [grid] = doc.tables
    cells = [[c.text for c in r.cells] for r in grid.rows]
    assert cells[0] == ["Titre", "Entité", "Échéance", "IBAN de paiement", "Montant"]
    assert cells[1] == ["OPCO contribution", ENTITY, "15 octobre 2026", IBAN,
                        "1 284,60 €"]  # fmt: skip


async def test_a_hidden_personal_document_is_left_out_on_telegram(api, payables):
    args = {"category": "payment_calls", "columns": ["title", "payment_iban"], "format": "csv"}
    web = await call("export_table", args)
    tg = await call("export_table", args, channel="telegram")
    assert (web.data["rows"], tg.data["rows"]) == (3, 2)
    _, raw = await _file(api, tg.data["export_id"])
    table = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
    assert [r[0] for r in table[1:]] == ["OPCO contribution", "URSSAF call"]
    assert table[1][1] == "FR •• 9012"
    by_id = await call("export_table", {"document_ids": [payables["personal"]],
                                        "columns": ["title"], "format": "csv"},
                       channel="telegram")  # fmt: skip
    assert by_id.is_error and by_id.data["error"]["code"] == "invalid_argument"


async def test_more_than_500_rows_is_truncated(api):
    batch = rows.batch()
    with rows.connect() as conn:
        conn.execute(
            "INSERT INTO documents (id, sha256, original_name, mime_type, size_bytes, source,"
            " batch_id, location, current_path, status, pipeline_stage, title, entity_id,"
            " category_id)"
            " SELECT 'doc_' || lpad(n::text, 26, '0'), md5(n::text) || md5(n::text),"
            " n || '.pdf', 'application/pdf', 1, 'drop', %s, 'inbox', n || '.pdf', 'review',"
            " 'done', 'Bulk ' || n, (SELECT id FROM entities WHERE key = 'cabinet'),"
            " 'payment_calls' FROM generate_series(1, 501) n",
            (batch,),
        )
    started = time.monotonic()
    res = await call("export_table", {"entity": "cabinet", "columns": COLUMNS, "format": "docx"})
    assert time.monotonic() - started < 10
    assert not res.is_error, res.text
    assert (res.data["rows"], res.data["truncated"]) == (500, True)
    pack, raw = await _file(api, res.data["export_id"])
    assert pack["truncated"] is True and pack["documentCount"] == 500
    assert len(DocxDocument(io.BytesIO(raw)).tables[0].rows) == 501


async def test_formula_looking_cells_are_guarded(api):
    w = World()
    b = w.batch()
    ids = [w.doc(t, batch=b, entity="cabinet", category="payment_calls") for t in INJECTIONS]
    csv_res = await call("export_table", {"document_ids": ids, "columns": ["title"],
                                          "format": "csv"})  # fmt: skip
    _, raw = await _file(api, csv_res.data["export_id"])
    table = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
    assert [r[0] for r in table[1:]] == ["'" + t for t in INJECTIONS]
    xlsx_res = await call("export_table", {"document_ids": ids, "columns": ["title"],
                                           "format": "xlsx"})  # fmt: skip
    _, raw = await _file(api, xlsx_res.data["export_id"])
    ws = load_workbook(io.BytesIO(raw)).active
    cells = [r[0] for r in ws.iter_rows(min_row=2)]
    assert [c.value for c in cells] == INJECTIONS and {c.data_type for c in cells} == {"s"}


async def test_the_export_card_activity_entry_and_downloads(api, payables):
    res = await call("export_table", {"document_ids": [payables["opco"]], "columns": ["title"],
                                      "format": "xlsx"})  # fmt: skip
    export_id = res.data["export_id"]
    assert [(c.kind, c.subject) for c in rows.card_rows()] == [("export", {"export_id": export_id})]
    f = T["file_ops"]
    with get_ctx().engine.connect() as conn:
        [entry] = conn.execute(select(f).where(f.c.action == "export")).mappings()
    assert (entry["actor"], entry["via"], entry["subject_id"], entry["undoable"]) == (
        "mona", "chat", export_id, False,
    )  # fmt: skip
    assert entry["after"]["format"] == "xlsx" and entry["after"]["rows"] == 1
    activity = (await api.get("/api/activity", params={"kind": "export"})).json()
    assert [i["entry"]["subjectId"] for i in activity["items"]] == [export_id]
    assert (await api.get(f"/api/exports/{export_id}/csv")).status_code == 404
    assert (await api.get(f"/api/exports/{export_id}/xlsx")).status_code == 200


async def test_no_matching_document_makes_no_file(payables):
    res = await call("export_table", {"query": "nothing like this", "columns": ["title"],
                                      "format": "xlsx"})  # fmt: skip
    assert res.is_error and res.data["error"]["code"] == "invalid_argument"
    assert "list_deadlines" in res.data["error"]["hint"]
    assert rows.card_rows() == [] and rows.all_rows("SELECT id FROM exports") == []


async def test_ids_and_filters_together_are_refused(payables):
    res = await call("export_table", {"document_ids": [payables["opco"]], "entity": "cabinet",
                                      "columns": ["title"], "format": "csv"})  # fmt: skip
    assert res.is_error and res.data["error"]["code"] == "invalid_argument"

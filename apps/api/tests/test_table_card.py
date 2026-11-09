"""A36: the inline table (`format="table"`), its `TableView` card, and the C2 table routes."""

import csv
import io
from datetime import date

import pytest
from sqlalchemy import select

from mona.app import create_app
from mona.db import get_engine
from mona.dto.load import card_payload
from mona.services.registry import T
from mona.workflow.common import get_ctx
from tests import rows
from tests.api_client import api_client
from tests.l4_world import World
from tests.mcp_http import call, list_tools

pytestmark = pytest.mark.usefixtures("l4_db")

IBAN = "FR7699999000010123456789012"
COLUMNS = ["title", "category", "due_date", "payment_iban", "amount"]


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


def _bulk(n: int) -> None:
    batch = rows.batch()
    with rows.connect() as conn:
        conn.execute(
            "INSERT INTO documents (id, sha256, original_name, mime_type, size_bytes, source,"
            " batch_id, location, current_path, status, pipeline_stage, title, entity_id,"
            " category_id, doc_date)"
            " SELECT 'doc_' || lpad(n::text, 26, '0'), md5(n::text) || md5(n::text),"
            " n || '.pdf', 'application/pdf', 1, 'drop', %s, 'inbox', n || '.pdf', 'review',"
            " 'done', 'Bulk ' || n, (SELECT id FROM entities WHERE key = 'cabinet'),"
            " 'payment_calls', date '2026-01-01' + n FROM generate_series(1, %s) n",
            (batch, n),
        )


def _delete(*ids: str) -> None:
    with rows.connect() as conn:
        conn.execute(
            "UPDATE documents SET deleted_at = now(), location = 'trash' WHERE id = ANY(%s)",
            (list(ids),),
        )


async def _payload(export_id: str) -> dict:
    async with get_engine().connect() as conn:
        found = await card_payload(conn, "table", export_id)
    assert found is not None
    return found


async def test_a_table_is_a_spec_an_activity_entry_and_a_card_without_a_file(payables):
    res = await call("export_table", {"has_due_date": True, "columns": COLUMNS,
                                      "format": "table", "title": "Payables"})  # fmt: skip
    assert not res.is_error, res.text
    export_id = res.data["export_id"]
    assert set(res.data) == {"export_id", "rows", "shown", "truncated", "empty_columns",
                             "card_refs", "note"}  # fmt: skip
    assert res.data["note"] == (
        "The person sees these rows as a table card under your reply. Don't write a table, a "
        "header row or any row values yourself; answer in one line and name any blank columns."
    )
    assert (res.data["rows"], res.data["shown"], res.data["truncated"]) == (3, 3, False)
    assert res.data["empty_columns"] == []
    x = T["exports"]
    with get_ctx().engine.connect() as conn:
        exp = conn.execute(select(x).where(x.c.id == export_id)).mappings().one()
        [entry] = conn.execute(
            select(T["file_ops"]).where(T["file_ops"].c.subject_id == export_id)
        ).mappings()
    assert (exp["format"], exp["status"], exp["title"], exp["file_path"]) == (
        "table", "ready", "Payables", None,
    )  # fmt: skip
    assert exp["spec"] == {
        "columns": COLUMNS,
        "document_ids": [payables["opco"], payables["urssaf"], payables["personal"]],
        "lang": "en",
    }
    assert (entry["actor"], entry["via"], entry["action"], entry["after"]["format"]) == (
        "mona", "chat", "export", "table",
    )  # fmt: skip
    [card] = rows.card_rows()
    assert (card.id, card.kind, card.subject) == (
        res.data["card_refs"][0], "table", {"export_id": export_id},
    )  # fmt: skip
    assert not (get_ctx().data_dir / "exports" / export_id).exists()


async def test_the_card_holds_the_first_50_rows_typed_and_labelled():
    _bulk(60)
    res = await call("export_table", {"entity": "cabinet", "columns": ["title", "category",
                                      "doc_date", "amount", "status"], "format": "table",
                                      "lang": "fr"})  # fmt: skip
    assert (res.data["rows"], res.data["shown"]) == (60, 50)
    view = await _payload(res.data["export_id"])
    assert (view["rowsTotal"], len(view["rows"]), view["lang"]) == (60, 50, "fr")
    assert view["emptyColumns"] == ["amount"]
    assert view["columns"][:3] == [
        {"key": "title", "label": "Titre"},
        {"key": "category", "label": "Catégorie"},
        {"key": "doc_date", "label": "Date"},
    ]
    assert view["rows"][0] == {
        "title": "Bulk 60", "category": "Appels de paiement", "doc_date": "2026-03-02",
        "amount": None, "currency": None, "status": "À vérifier",
    }  # fmt: skip


async def test_amounts_are_numbers_with_their_currency(payables):
    res = await call("export_table", {"document_ids": [payables["opco"]],
                                      "columns": ["amount", "due_date"],
                                      "format": "table"})  # fmt: skip
    view = await _payload(res.data["export_id"])
    assert view["rows"] == [{"amount": 1284.6, "currency": "EUR", "due_date": "2026-10-15"}]


async def test_the_card_is_built_from_current_state(payables):
    res = await call("export_table", {"has_due_date": True, "columns": ["title"],
                                      "format": "table"})  # fmt: skip
    _delete(payables["urssaf"])
    with rows.connect() as conn:
        conn.execute("UPDATE documents SET title = 'OPCO 2026' WHERE id = %s", (payables["opco"],))
    view = await _payload(res.data["export_id"])
    assert [r["title"] for r in view["rows"]] == ["OPCO 2026", "Personal tax"]
    assert view["rowsTotal"] == 2


async def test_on_telegram_the_result_carries_a_server_built_text(payables):
    _bulk(25)
    res = await call("export_table", {"category": "payment_calls",
                                      "columns": ["title", "due_date", "payment_iban", "amount"],
                                      "format": "table", "title": "Payables"},
                     channel="telegram")  # fmt: skip
    assert not res.is_error, res.text
    assert res.data["rows"] == 27
    lines = res.data["text"].split("\n")
    assert lines[:2] == ["Payables", "Title · Due date · Payment IBAN · Amount"]
    assert len([x for x in lines if x.startswith("- ")]) == 20
    assert "- OPCO contribution · 15 October 2026 · FR •• 9012 · €1,284.60" in lines
    assert IBAN not in res.data["text"] and "Personal tax" not in res.data["text"]
    assert lines[-1] == "… and 7 more"
    web = await call("export_table", {"document_ids": [payables["opco"]], "columns": ["title"],
                                      "format": "table"})  # fmt: skip
    assert "text" not in web.data
    assert "note" not in res.data


async def test_the_description_steers_tables_inline_and_names_empty_columns():
    [tool] = [t for t in await list_tools() if t["name"] == "export_table"]
    text = tool["description"]
    assert "For a table the person wants to see, use format table; it appears in the chat." in text
    assert "only when the person asks for a file, Excel, Word or CSV" in text
    assert "When empty_columns is not empty, tell the person which columns came out blank." in text
    assert "On Telegram, send the result's text as it is." in text
    assert tool["inputSchema"]["properties"]["format"]["enum"] == ["csv", "xlsx", "docx", "table"]


async def test_get_table_refreshes_the_card(api, payables):
    res = await call("export_table", {"has_due_date": True, "columns": COLUMNS,
                                      "format": "table"})  # fmt: skip
    export_id = res.data["export_id"]
    got = await api.get(f"/api/exports/{export_id}/table")
    assert got.status_code == 200, got.text
    assert got.json() == await _payload(export_id)
    assert got.json()["emptyColumns"] == []
    pack = (await api.get(f"/api/exports/{export_id}")).json()
    assert (pack["format"], pack["fileUrl"]) == ("table", None)


async def test_the_table_routes_refuse_a_file_export_and_an_emptied_table(api, payables):
    file = await call("export_table", {"document_ids": [payables["opco"]], "columns": ["title"],
                                       "format": "csv"})  # fmt: skip
    for res in (
        await api.get(f"/api/exports/{file.data['export_id']}/table"),
        await api.post(f"/api/exports/{file.data['export_id']}/file", json={"format": "csv"}),
        await api.get("/api/exports/exp_00000000000000000000000000/table"),
    ):
        assert res.status_code == 404 and res.json()["error"]["code"] == "not_found"
    table = await call("export_table", {"document_ids": [payables["opco"]], "columns": ["title"],
                                        "format": "table"})  # fmt: skip
    _delete(payables["opco"])
    for res in (
        await api.get(f"/api/exports/{table.data['export_id']}/table"),
        await api.post(f"/api/exports/{table.data['export_id']}/file", json={"format": "xlsx"}),
    ):
        assert res.status_code == 409, res.text
        assert res.json()["error"]["code"] == "conflict"
        assert res.json()["error"]["details"] == {"reason": "empty"}


async def test_download_as_builds_a_file_from_the_spec_by_the_person(api, payables):
    res = await call("export_table", {"has_due_date": True, "columns": ["title", "payment_iban"],
                                      "format": "table", "title": "Payables"})  # fmt: skip
    export_id = res.data["export_id"]
    cnv = rows.conversation()
    made = await api.post(f"/api/exports/{export_id}/file",
                          json={"format": "csv", "conversationId": cnv})  # fmt: skip
    assert made.status_code == 201, made.text
    pack = made.json()
    assert pack["id"] != export_id
    assert (pack["format"], pack["title"], pack["documentCount"]) == ("csv", "Payables", 3)
    raw = (await api.get(pack["fileUrl"])).content
    table = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
    assert table == [
        ["title", "payment_iban"],
        ["OPCO contribution", IBAN],
        ["URSSAF call", ""],
        ["Personal tax", IBAN],
    ]
    f = T["file_ops"]
    with get_ctx().engine.connect() as conn:
        [entry] = conn.execute(select(f).where(f.c.subject_id == pack["id"])).mappings()
    assert (entry["actor"], entry["via"], entry["after"]["format"]) == ("user", "ui", "csv")
    assert [n.text for n in rows.notes_of(cnv)] == [
        'Downloaded the table "Payables" as CSV (3 rows).'
    ]
    assert rows.card_rows()[1:] == []
    plain = await api.post(f"/api/exports/{export_id}/file", json={"format": "docx"})
    assert plain.status_code == 201 and len(rows.notes_of(cnv)) == 1
    bad = await api.post(f"/api/exports/{export_id}/file", json={"format": "table"})
    assert bad.status_code == 400

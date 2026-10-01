"""C2 §10/§12 and C4 §3.10–§3.13: deadlines, reminders, drafts, accountant exports."""

import csv
import io
import zipfile
from datetime import timedelta

import pytest
from docx import Document as DocxDocument
from sqlalchemy import select

from mona import clock
from mona.app import create_app
from mona.i18n import format_date
from mona.services.registry import T
from mona.workflow import drafts, exports
from mona.workflow.common import get_ctx
from tests import rows
from tests.api_client import api_client
from tests.l4_world import World
from tests.mcp_http import call

pytestmark = pytest.mark.usefixtures("l4_db")
TODAY = clock.paris_today()


@pytest.fixture
async def api():
    async with api_client(create_app()) as c:
        yield c


def journal(action: str) -> list:
    f = T["file_ops"]
    with get_ctx().engine.connect() as conn:
        return list(conn.execute(select(f).where(f.c.action == action)).mappings())


# --- §10 deadlines ---


@pytest.fixture
def due():
    w = World()
    vb = w.batch(visitor=True)
    visitor_doc = rows.document("Visitor bill", entity="visitors", category=None, batch_id=vb)
    urssaf = rows.document("URSSAF call", entity="cabinet", due_date=TODAY + timedelta(days=3))
    return {
        "soon": rows.deadline("URSSAF", TODAY + timedelta(days=3), amount=412.0,
                              document_id=urssaf),
        "overdue": rows.deadline("Late", TODAY - timedelta(days=2)),
        "far": rows.deadline("Far", TODAY + timedelta(days=90)),
        "done": rows.deadline("Paid", TODAY + timedelta(days=1), status="done"),
        "personal": rows.deadline("Tax", TODAY + timedelta(days=5), entity="personal"),
        "visitor": rows.deadline("Visitor's bill", TODAY + timedelta(days=2), entity="visitors",
                                 document_id=visitor_doc),
    }  # fmt: skip


async def test_deadlines_list_leaves_out_visitors_and_filters(api, due):
    res = await api.get("/api/deadlines")
    assert res.status_code == 200
    ids = [d["id"] for d in res.json()["items"]]
    assert ids == [due["overdue"], due["soon"], due["personal"]]
    assert res.json()["items"][1]["amount"] == {"value": 412.0, "currency": "EUR"}
    assert res.json()["items"][1]["daysLeft"] == 3
    done = await api.get("/api/deadlines", params={"status": "done"})
    assert [d["id"] for d in done.json()["items"]] == [due["done"]]
    upcoming = await api.get("/api/deadlines", params={"includeOverdue": "false",
                                                       "withinDays": 120})  # fmt: skip
    assert [d["id"] for d in upcoming.json()["items"]] == [due["soon"], due["personal"],
                                                           due["far"]]  # fmt: skip


async def test_list_deadlines_tool_shares_the_query(due):
    web = await call("list_deadlines", {})
    assert [i["deadline_id"] for i in web.data["items"]] == [due["overdue"], due["soon"],
                                                             due["personal"]]  # fmt: skip
    tg = await call("list_deadlines", {}, channel="telegram")
    assert [i["deadline_id"] for i in tg.data["items"]] == [due["overdue"], due["soon"]]


async def rest_ids(api) -> list[str]:
    return [d["id"] for d in (await api.get("/api/deadlines")).json()["items"]]


async def tool_ids(channel: str = "web") -> list[str]:
    return [
        i["deadline_id"] for i in (await call("list_deadlines", {}, channel=channel)).data["items"]
    ]


async def test_rest_and_the_tool_on_both_channels_list_through_one_visibility_filter(api, due):
    w = World()
    unsorted = rows.document("Unsorted letter", entity=None, category=None, status="review")
    deleted = rows.document("Deleted call", deleted=True)
    in_visitor_batch = rows.document("Visitor call", batch_id=w.batch(visitor=True))
    more = {
        "unsorted": rows.deadline("Unsorted", TODAY + timedelta(days=4), document_id=unsorted),
        "deleted": rows.deadline("Deleted", TODAY + timedelta(days=4), document_id=deleted),
        "visitor": rows.deadline("Visitor", TODAY + timedelta(days=4),
                                 document_id=in_visitor_batch),
    }  # fmt: skip
    web = [due["overdue"], due["soon"], more["unsorted"], due["personal"]]
    assert await rest_ids(api) == web
    assert await tool_ids("web") == web
    assert await tool_ids("telegram") == [due["overdue"], due["soon"]]


async def test_rest_and_the_tool_call_the_same_query(api, due, monkeypatch):
    from mona import brief

    seen: list[str] = []
    shared = brief.deadline_query

    def spy(scope, *clauses, **kw):
        seen.append(scope.channel)
        return shared(scope, *clauses, **kw)

    monkeypatch.setattr(brief, "deadline_query", spy)
    await rest_ids(api)
    await tool_ids("web")
    await tool_ids("telegram")
    assert seen == ["web", "web", "telegram"]


async def test_deadline_done_and_reopen(api, due):
    res = await api.patch(f"/api/deadlines/{due['soon']}", json={"status": "done"})
    assert res.status_code == 200 and res.json()["status"] == "done"
    back = await api.patch(f"/api/deadlines/{due['soon']}", json={"status": "open"})
    assert back.json()["status"] == "open"
    assert journal("deadline.change") == []
    missing = await api.patch("/api/deadlines/ddl_01m3sg44rengv1yevkp7ca1xg5",
                              json={"status": "done"})  # fmt: skip
    assert missing.status_code == 404


# --- §10 / C4 §3.11 reminders ---


async def test_reminders_rest_idempotent_and_journaled(api, due):
    cnv = rows.conversation()
    body = {"deadlineId": due["soon"], "remindOn": str(TODAY + timedelta(days=1)),
            "conversationId": cnv}  # fmt: skip
    first = await api.post("/api/reminders", json=body)
    assert first.status_code == 201
    out = first.json()
    assert out["created"] is True and out["deadline"]["reminder"]["id"] == out["reminderId"]
    again = await api.post("/api/reminders", json=body)
    assert again.status_code == 200 and again.json()["reminderId"] == out["reminderId"]
    [entry] = journal("reminder.add")
    assert (entry["actor"], entry["via"], entry["subject_id"]) == ("user", "ui", out["reminderId"])
    texts = [n.text for n in rows.notes_of(cnv)]
    assert texts[0] == f'Set a reminder for "URSSAF" on {TODAY + timedelta(days=1)}.'
    past = await api.post("/api/reminders", json={**body, "remindOn": str(TODAY - timedelta(1))})
    assert past.status_code == 422 and past.json()["error"]["field"] == "remindOn"
    deleted = await api.delete(f"/api/reminders/{out['reminderId']}")
    assert deleted.status_code == 204


async def test_schedule_reminder_tool(due):
    doc = rows.document("SIE letter", entity="cabinet")
    args = {"deadline_id": due["soon"], "remind_on": str(TODAY), "note": "call them"}
    res = await call("schedule_reminder", args)
    assert not res.is_error, res.text
    assert res.data["created"] is True and res.data["deadline_id"] == due["soon"]
    again = await call("schedule_reminder", {"deadline_id": due["soon"], "remind_on": str(TODAY)})
    assert again.data["created"] is False and again.data["reminder_id"] == res.data["reminder_id"]
    on_doc = await call("schedule_reminder", {"document_id": doc, "remind_on": str(TODAY)})
    kinds = [(c.tool, c.kind) for c in rows.card_rows()]
    assert kinds == [("schedule_reminder", "deadline")] * 2 + [("schedule_reminder", "doc")]
    assert on_doc.data["document_id"] == doc
    [a, b] = journal("reminder.add")
    assert (a["actor"], a["via"]) == ("mona", "chat")
    yesterday = str(TODAY - timedelta(days=1))
    past = await call("schedule_reminder", {"deadline_id": due["soon"], "remind_on": yesterday})
    assert past.data["error"]["code"] == "invalid_argument"
    args = {"deadline_id": due["personal"], "remind_on": str(TODAY)}
    hidden = await call("schedule_reminder", args, channel="telegram")
    assert hidden.data["error"]["code"] == "not_found"
    tg = await call("schedule_reminder", {"deadline_id": due["soon"],
                                          "remind_on": str(TODAY + timedelta(2))},
                    channel="telegram")  # fmt: skip
    assert journal("reminder.add")[-1]["via"] == "telegram" and tg.data["created"]


# --- §12 / C4 §3.12 drafts ---


class DraftModel:
    model = "recorded"

    def __init__(self, title: str, body: str):
        self.title, self.body, self.calls = title, body, []

    def complete_json(self, system, user, schema, **kw):
        self.calls.append((system, user))
        return {"title": self.title, "body": self.body}


async def test_draft_reply_in_the_filing_language_then_docx(api):
    doc = rows.document("SIE avis de mise en recouvrement", entity="cabinet",
                        text="Montant dû 1 250,00 €")  # fmt: skip
    res = await call("draft_reply", {"document_id": doc, "instructions": "ask for a schedule"})
    assert not res.is_error, res.text
    assert set(res.data) == {"draft_id", "status", "card_refs"}
    draft_id = res.data["draft_id"]
    [card] = rows.card_rows()
    assert (card.kind, card.subject) == ("draft", {"draft_id": draft_id})
    row = rows.one("SELECT lang, status FROM drafts WHERE id = %s", (draft_id,))
    assert (row.lang, row.status) == ("fr", "generating")
    early = await api.get(f"/api/drafts/{draft_id}/docx")
    assert early.status_code == 404 and early.json()["error"]["code"] == "not_ready"
    model = DraftModel(
        "Demande d'échéancier", "Madame, Monsieur,\n\nRéf. [RÉFÉRENCE]\n\nCordialement"
    )
    assert drafts.generate_draft(get_ctx(), draft_id, model_factory=lambda: model) == "ready"
    system, user = model.calls[0]
    assert "Write in French" in system and "ask for a schedule" in user
    got = await api.get(f"/api/drafts/{draft_id}")
    assert got.json()["status"] == "ready"
    assert got.json()["docxUrl"] == f"/api/drafts/{draft_id}/docx"
    cnv = rows.conversation()
    file = await api.get(f"/api/drafts/{draft_id}/docx", params={"conversationId": cnv})
    assert file.status_code == 200
    assert file.headers["content-disposition"].startswith("attachment;")
    paragraphs = [p.text for p in DocxDocument(io.BytesIO(file.content)).paragraphs]
    assert paragraphs[0] == format_date(TODAY, "fr")
    assert paragraphs[1:] == ["Madame, Monsieur,", "Réf. [RÉFÉRENCE]", "Cordialement"]
    assert [n.text for n in rows.notes_of(cnv)] == ['Downloaded the draft "Demande d\'échéancier".']


async def test_romanian_drafts_use_comma_below_and_hidden_documents_are_not_found():
    doc = rows.document("Letter", entity="cabinet")
    res = await call("draft_reply", {"document_id": doc, "lang": "ro"})
    model = DraftModel("Cerere", "Vă rugăm să ne transmiteţi [DATA]; mulţumim, şi")
    drafts.generate_draft(get_ctx(), res.data["draft_id"], model_factory=lambda: model)
    body = rows.one("SELECT body FROM drafts WHERE id = %s", (res.data["draft_id"],)).body
    assert body == "Vă rugăm să ne transmiteți [DATA]; mulțumim, și"
    personal = rows.document("Tax", entity="personal")
    hidden = await call("draft_reply", {"document_id": personal}, channel="telegram")
    assert hidden.data["error"]["code"] == "not_found"


async def test_a_draft_whose_model_fails_twice_is_failed():
    from mona.interviews.model import ModelError

    class Broken:
        def complete_json(self, *a, **kw):
            raise ModelError("transport")

    doc = rows.document("Letter", entity="cabinet")
    res = await call("draft_reply", {"document_id": doc})
    assert drafts.generate_draft(get_ctx(), res.data["draft_id"],
                                 model_factory=lambda: Broken()) == "failed"  # fmt: skip


# --- §12 / C4 §3.13 exports ---

INJECTIONS = ['=HYPERLINK("http://x","OPCO")', "+33 call", "-5 credit", "@SUM(A1)",
              "\tTabbed", "\rCarriage"]  # fmt: skip


@pytest.fixture
def pack():
    w = World()
    b = w.batch()
    ids = [
        w.doc(title, batch=b, status="filed", reasons=[], entity="cabinet",
              category="payment_calls", counterparty="opco", path=f"Cabinet Marchand/p-{n}.pdf",
              fiscal_year=2025, doc_date="2025-02-01", amount=100 + n)
        for n, title in enumerate(INJECTIONS)
    ]  # fmt: skip
    w.doc("in review", batch=b, entity="cabinet", fiscal_year=2025)
    w.doc("other year", batch=b, status="filed", reasons=[], entity="cabinet",
          path="Cabinet Marchand/old.pdf", fiscal_year=2024)  # fmt: skip
    w.doc("personal", batch=b, status="filed", reasons=[], entity="personal",
          path="Personnel/x.pdf", fiscal_year=2025)  # fmt: skip
    return w, ids


async def test_export_preview_and_refusals(api, pack):
    w, ids = pack
    ents = w.ids("entities")
    res = await api.get("/api/exports/preview", params={"entityId": ents["cabinet"],
                                                        "fiscalYear": 2025})  # fmt: skip
    assert res.status_code == 200
    assert res.json() == {
        "entityId": ents["cabinet"], "fiscalYear": 2025, "documentCount": len(INJECTIONS),
        "inReview": 1, "categories": [{"id": "payment_calls", "label": "Payment calls",
                                       "count": len(INJECTIONS)}],
        "fiscalYears": [2025, 2024],
    }  # fmt: skip
    for key in ("personal", "visitors"):
        p = await api.get("/api/exports/preview", params={"entityId": ents[key],
                                                          "fiscalYear": 2025})  # fmt: skip
        b = await api.post("/api/exports", json={"entityId": ents[key], "fiscalYear": 2025})
        assert p.status_code == b.status_code == 403
        assert b.json()["error"]["code"] == "not_allowed"
    for channel in ("web", "telegram"):
        for entity in ("Personnel", "Visitors"):
            r = await call("export_accountant_pack", {"entity": entity, "fiscal_year": 2025},
                           channel=channel)  # fmt: skip
            assert r.data["error"]["code"] == "not_allowed", (channel, entity, r.text)


async def test_build_zip_and_formula_safe_csv(api, pack):
    w, ids = pack
    res = await call("export_accountant_pack", {"entity": "cabinet", "fiscal_year": 2025})
    assert not res.is_error, res.text
    assert (res.data["status"], res.data["document_count"]) == ("building", len(INJECTIONS))
    export_id = res.data["export_id"]
    again = await call("export_accountant_pack", {"entity": "Cabinet Marchand",
                                                  "fiscal_year": 2025})  # fmt: skip
    assert again.data["export_id"] == export_id
    assert [c.kind for c in rows.card_rows()] == ["export", "export"]
    assert len(w.job_rows("build_export")) == 1
    not_yet = await api.get(f"/api/exports/{export_id}/zip")
    assert not_yet.status_code == 404 and not_yet.json()["error"]["code"] == "not_ready"
    assert exports.build_export(get_ctx(), export_id) == "ready"
    pack_ = (await api.get(f"/api/exports/{export_id}")).json()
    assert pack_["status"] == "ready" and pack_["zipUrl"] and pack_["csvUrl"]
    z = await api.get(pack_["zipUrl"])
    names = zipfile.ZipFile(io.BytesIO(z.content)).namelist()
    assert sorted(n for n in names if n.endswith(".pdf")) == sorted(
        f"Cabinet Marchand/p-{n}.pdf" for n in range(len(INJECTIONS))
    )
    raw = (await api.get(pack_["csvUrl"])).content.decode("utf-8-sig")
    table = list(csv.reader(io.StringIO(raw)))
    assert table[0][:3] == ["Fichier", "Titre", "Date"]
    titles = sorted(r[1] for r in table[1:])
    assert titles == sorted("'" + t for t in INJECTIONS)
    assert all(not cell.startswith(tuple("=+-@\t\r")) for r in table for cell in r)
    fresh = await api.post("/api/exports", json={"entityId": w.ids("entities")["cabinet"],
                                                 "fiscalYear": 2025})  # fmt: skip
    assert fresh.status_code == 201 and fresh.json()["id"] != export_id
    listed = await api.get("/api/exports")
    assert listed.json()["total"] == 2

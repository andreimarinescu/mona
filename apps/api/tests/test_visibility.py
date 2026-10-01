"""C9 §8 test 3 (visibility) beyond the read-tool tests, and C2 §17 item 9 on REST."""

from datetime import timedelta

import pytest

from mona import clock
from mona.app import create_app
from tests import rows
from tests.api_client import api_client
from tests.mcp_http import call

pytestmark = pytest.mark.usefixtures("clean")

TODAY = clock.paris_today()


@pytest.fixture
def world() -> dict[str, str]:
    visitor_batch = rows.batch()
    rows.connect().execute("UPDATE batches SET visitor = true WHERE id = %s", (visitor_batch,))
    w = {
        "visitor": rows.document("Stranger's bill", entity="visitors", category="payment_calls",
                                 amount=77.0, batch_id=visitor_batch),
        "personal": rows.document("Private letter", entity="personal", category="tax",
                                  amount=40.0),
        "practice": rows.document("Practice invoice", entity="cabinet", amount=100.0),
        "orphan": rows.document("No entity yet", entity=None, category=None, status="review",
                                reasons=("entity",)),
    }  # fmt: skip
    w["visitor_deadline"] = rows.deadline(
        "Stranger's due date", TODAY + timedelta(days=1), entity="visitors",
        document_id=w["visitor"], amount=77.0,
    )  # fmt: skip
    w["practice_deadline"] = rows.deadline("Practice due", TODAY + timedelta(days=2), amount=1.0)
    rows.reminder(TODAY, document_id=w["personal"])
    rows.reminder(TODAY, document_id=w["practice"])
    return w


async def test_telegram_hides_visitors_personal_and_entityless_documents(world):
    for key in ("visitor", "personal", "orphan"):
        tg = await call("get_document", {"document_id": world[key]}, channel="telegram")
        assert tg.data["error"]["code"] == "not_found", key
        assert not (await call("get_document", {"document_id": world[key]})).is_error
    tg = await call("search_documents", {"limit": 25}, channel="telegram")
    assert [r["id"] for r in tg.data["results"]] == [world["practice"]]
    tg_sum = await call("sum_amounts", {"amount_min": 0}, channel="telegram")
    assert tg_sum.data["totals"] == [{"currency": "EUR", "total": 100.0}]
    brief = await call("get_brief", channel="telegram")
    assert [r["label"] for r in brief.data["reminders_today"]] == ["Practice invoice"]
    assert brief.data["filed"]["count"] == 1
    assert "Stranger" not in brief.text and "Private" not in brief.text


async def test_the_web_lists_visitors_documents_but_leaves_them_out_of_every_figure(world):
    web = await call("search_documents", {"limit": 25})
    assert world["visitor"] in {r["id"] for r in web.data["results"]}
    sums = await call("sum_amounts", {"amount_min": 0})
    assert sums.data["totals"] == [{"currency": "EUR", "total": 140.0}]
    by_id = await call("sum_amounts", {"document_ids": [world["visitor"]]})
    assert by_id.data["count"] == 0
    deadlines = await call("list_deadlines")
    assert [i["label"] for i in deadlines.data["items"]] == ["Practice due"]
    brief = await call("get_brief")
    assert brief.data["filed"]["count"] == 2
    assert [d["label"] for d in brief.data["due_soon"]] == ["Practice due"]
    assert sorted(r["label"] for r in brief.data["reminders_today"]) == [
        "Practice invoice", "Private letter",
    ]  # fmt: skip


async def test_pending_interview_counts_only_visible_questions_on_telegram(world):
    iid = rows.interview(open_questions=2)
    with rows.connect() as conn:
        qs = [r.id for r in conn.execute(
            "SELECT id FROM interview_questions WHERE interview_id = %s ORDER BY ordinal", (iid,)
        )]  # fmt: skip
        conn.execute("UPDATE interview_questions SET affected_document_ids = %s WHERE id = %s",
                     ([world["personal"]], qs[0]))  # fmt: skip
        conn.execute("UPDATE interview_questions SET affected_document_ids = %s WHERE id = %s",
                     ([world["practice"]], qs[1]))  # fmt: skip
    web = await call("get_brief")
    tg = await call("get_brief", channel="telegram")
    assert web.data["pending_interview"] == {"interview_id": iid, "open_questions": 2}
    assert tg.data["pending_interview"] == {"interview_id": iid, "open_questions": 1}


async def test_rest_home_leaves_visitors_out_and_the_web_sees_personal_entities(world, l2_world):
    app = create_app()
    async with api_client(app) as cl:
        home = (await cl.get("/api/home")).json()
        found = (await cl.get("/api/documents", params={"limit": 50})).json()
        personal = await cl.get(f"/api/documents/{world['personal']}")
    assert [d["label"] for d in home["facts"]["dueSoon"]] == ["Practice due"]
    assert home["due"]["total"] == 1 and home["facts"]["filed"]["count"] == 2
    assert {world["personal"], world["visitor"]} <= {d["id"] for d in found["items"]}
    assert personal.status_code == 200 and personal.json()["entityName"]

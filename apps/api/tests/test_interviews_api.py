"""C2 §11 endpoints (test 17, notes, polling) and the C4 §3.6/§3.7 tools (tests 12, 16)."""

import pytest
from sqlalchemy import select

from mona.app import create_app
from mona.interviews import answers, service
from mona.interviews.generate import generate_interview
from mona.services.registry import T
from tests import rows
from tests.api_client import api_client
from tests.l4_world import RecordedModel, World, fixture
from tests.mcp_http import call

pytestmark = pytest.mark.usefixtures("l4_db")


@pytest.fixture
async def api():
    async with api_client(create_app()) as c:
        yield c


def agipi_only(w: World) -> tuple[str, str]:
    """A batch debrief with the one AGIPI `depends` question, ready."""
    spec = fixture("cluster.json")
    b = w.batch()
    w.cluster(b, {"docs": [d for d in spec["docs"] if d["tag"].startswith("agipi")]})
    interview_id = service.start(w.ctx, {"type": "batch", "batch_id": b}, lang="en").interview_id
    pass2 = {"questions": spec["pass2"]["questions"][:1]}
    model = RecordedModel(w, pass2=pass2)
    assert generate_interview(w.ctx, interview_id, model_factory=lambda: model) == "ready"
    [q] = w.questions(interview_id)
    return interview_id, q["id"]


def notes(conversation_id: str) -> list:
    return [(n.text,) for n in rows.notes_of(conversation_id)]


def note_kinds(conversation_id: str) -> list[str]:
    return [
        r.kind
        for r in rows.all_rows(
            "SELECT kind FROM card_action_notes WHERE conversation_id = %s ORDER BY created_at",
            (conversation_id,),
        )
    ]


# --- C2 §17 test 17 ---


async def test_answer_repeat_apply_all_and_conflicts(api):
    w = World()
    interview_id, qid = agipi_only(w)
    base = f"/api/interviews/{interview_id}/questions/{qid}"
    res = await api.post(f"{base}/answer", json={"optionId": "a"})
    assert res.status_code == 200
    body = res.json()
    assert body["interviewStatus"] == "done"
    assert body["question"]["answer"]["optionId"] == "a"
    assert [r["state"] for r in body["rules"]] == ["draft", "draft"]
    assert len(body["previews"]) == 2 and body["previews"][0]["movesTotal"] == 1
    again = await api.post(f"{base}/answer", json={"optionId": "a"})
    assert again.status_code == 200
    assert [r["id"] for r in again.json()["rules"]] == [r["id"] for r in body["rules"]]
    applied = await api.post(f"{base}/apply", json={})
    assert applied.status_code == 200
    results = applied.json()["results"]
    assert [r["preview"]["rule"]["id"] for r in results] == [r["id"] for r in body["rules"]]
    assert [r["moved"] for r in results] == [1, 2] and all(r["groupId"] for r in results)
    other = await api.post(f"{base}/answer", json={"optionId": "b"})
    assert other.status_code == 409
    err = other.json()["error"]
    assert err["code"] == "already_answered"
    assert err["details"]["answer"] == {"optionId": "a", "freeText": None}


async def test_answering_a_generating_interview_is_not_ready(api):
    w = World()
    interview_id, qid = agipi_only(w)
    from sqlalchemy import update

    with w.engine.begin() as conn:
        i = T["interviews"]
        conn.execute(update(i).where(i.c.id == interview_id).values(status="generating"))
    res = await api.post(
        f"/api/interviews/{interview_id}/questions/{qid}/answer", json={"optionId": "a"}
    )
    assert res.status_code == 409
    assert res.json()["error"] == {
        "code": "conflict",
        "message": "The interview isn't ready.",
        "details": {"reason": "interview_not_ready"},
    }


async def test_answer_body_needs_exactly_one_of_option_and_free_text(api):
    w = World()
    interview_id, qid = agipi_only(w)
    base = f"/api/interviews/{interview_id}/questions/{qid}/answer"
    both = await api.post(base, json={"optionId": "a", "freeText": "x"})
    assert both.status_code == 400 and both.json()["error"]["code"] == "invalid_request"
    unknown = await api.post(base, json={"optionId": "z"})
    assert unknown.status_code == 422 and unknown.json()["error"]["field"] == "optionId"


async def test_ids_with_the_wrong_prefix_are_not_found(api):
    for path in ("/api/interviews/doc_01m3sg44rengv1yevkp7ca1xg5",
                 "/api/interviews/int_01m3sg44rengv1yevkp7ca1xg5"):  # fmt: skip
        res = await api.get(path)
        assert res.status_code == 404 and res.json()["error"]["code"] == "not_found"


# --- create, reuse, get, list, cancel ---


async def test_create_then_reuse_and_the_empty_scope(api):
    w = World()
    b = w.batch()
    w.cluster(b)
    first = await api.post("/api/interviews", json={"scope": {"type": "batch", "batchId": b}})
    assert first.status_code == 201
    created = first.json()
    assert created["reused"] is False
    iv = created["interview"]
    assert (iv["kind"], iv["status"], iv["questions"], iv["source"]) == (
        "debrief", "generating", [], None,
    )  # fmt: skip
    assert iv["scope"] == {"type": "batch", "batchId": b} and iv["lang"] == "en"
    again = await api.post("/api/interviews", json={"scope": {"type": "batch", "batchId": b}})
    assert again.status_code == 200 and again.json()["reused"] is True
    assert again.json()["interview"]["id"] == iv["id"]
    empty = await api.post("/api/interviews", json={"scope": {"type": "seed"}, "lang": "fr"})
    assert empty.status_code == 201
    wrong = await api.post("/api/interviews", json={"scope": {"type": "batch", "batchId": "doc_x"}})
    assert wrong.status_code == 400


async def test_an_empty_scope_is_422_on_scope(api):
    w = World()
    b = w.batch()
    res = await api.post("/api/interviews", json={"scope": {"type": "batch", "batchId": b}})
    assert res.status_code == 422
    assert (res.json()["error"]["code"], res.json()["error"]["field"]) == ("invalid_value", "scope")


async def test_polling_moves_generating_to_ready_with_etags(api):
    w = World()
    b = w.batch()
    w.cluster(b)
    iv = (await api.post("/api/interviews", json={"scope": {"type": "queue"}})).json()["interview"]
    one = await api.get(f"/api/interviews/{iv['id']}")
    tag = one.headers["etag"]
    assert tag.startswith('W/"') and one.json()["status"] == "generating"
    cached = await api.get(f"/api/interviews/{iv['id']}", headers={"if-none-match": tag})
    assert cached.status_code == 304
    generate_interview(w.ctx, iv["id"], model_factory=lambda: RecordedModel(w))
    two = await api.get(f"/api/interviews/{iv['id']}", headers={"if-none-match": tag})
    assert two.status_code == 200 and two.json()["status"] == "ready"
    body = two.json()
    assert body["openQuestions"] == 5 and body["source"] == "live" and body["readyAt"]
    assert body["questions"][0]["evidence"][0]["documentTitle"]
    listed = await api.get("/api/interviews", params={"status": "ready"})
    assert listed.json()["total"] == 1 and listed.json()["items"][0]["id"] == iv["id"]


async def test_cancel(api):
    w = World()
    w.cluster(w.batch())
    iv = (await api.post("/api/interviews", json={"scope": {"type": "queue"}})).json()["interview"]
    res = await api.post(f"/api/interviews/{iv['id']}/cancel")
    assert res.status_code == 200 and res.json()["status"] == "cancelled"


# --- C2 §14 notes ---


async def test_card_actions_write_their_notes_in_the_conversation(api):
    w = World()
    b = w.batch()
    w.cluster(b)
    interview_id = service.start(w.ctx, {"type": "batch", "batch_id": b}, lang="en").interview_id
    generate_interview(w.ctx, interview_id, model_factory=lambda: RecordedModel(w))
    qs = {q["text"]: q["id"] for q in w.questions(interview_id)}
    cnv = rows.conversation()
    base = f"/api/interviews/{interview_id}/questions"
    agipi = qs["How should AGIPI documents be filed?"]
    hello = qs["Are the Hello bank statements the LMNP account?"]
    unim = qs["Is UNIM the practice's provident insurer?"]
    bois = qs["Which site are the Atelier Bois & Co works for?"]
    await api.post(f"{base}/{agipi}/answer", json={"optionId": "a", "conversationId": cnv})
    await api.post(f"{base}/{hello}/answer", json={"optionId": "c", "conversationId": cnv})
    await api.post(f"{base}/{unim}/answer", json={"freeText": "It's the SELARL's.",
                                                  "conversationId": cnv})  # fmt: skip
    await api.post(f"{base}/{bois}/skip", json={"conversationId": cnv})
    await api.post(f"{base}/{agipi}/apply", json={"conversationId": cnv})
    await api.post(f"{base}/{agipi}/apply", json={"conversationId": rows.conversation()})
    texts = [t for (t,) in notes(cnv)]
    assert note_kinds(cnv) == [
        "interview.answer", "interview.answer", "interview.answer_text", "interview.skip",
        "rule.apply", "rule.apply",
    ]  # fmt: skip
    assert texts[0].startswith('Answered interview question "How should AGIPI documents be')
    assert "2 rule(s) drafted:" in texts[0]
    assert texts[1] == (
        'Answered interview question "Are the Hello bank statements the LMNP account?" with '
        '"Ask me each time". 1 rule created: "Hello bank · Ask me each time" (documents like '
        "these will always come to review)."
    )
    assert texts[2] == (
        'Answered interview question "Is UNIM the practice\'s provident insurer?" in their own '
        "words: \"It's the SELARL's.\". No rule was drafted."
    )
    assert (
        texts[3] == 'Skipped interview question "Which site are the Atelier Bois & Co works for?".'
    )
    assert texts[4].endswith(": 1 documents moved, 0 already in place.")


async def test_a_failing_answer_writes_no_note(api):
    w = World()
    interview_id, qid = agipi_only(w)
    cnv = rows.conversation()
    await api.post(
        f"/api/interviews/{interview_id}/questions/{qid}/answer",
        json={"optionId": "a", "conversationId": cnv},
    )
    await api.post(
        f"/api/interviews/{interview_id}/questions/{qid}/answer",
        json={"optionId": "b", "conversationId": cnv},
    )
    assert note_kinds(cnv) == ["interview.answer"]


# --- C4 §3.6 / §3.7 tools ---


def cards() -> list:
    return rows.card_rows()


async def test_start_interview_reuses_with_a_fresh_card_and_no_second_job():
    w = World()
    b = w.batch()
    w.cluster(b)
    first = await call("start_interview", {"batch_id": b})
    assert not first.is_error, first.text
    assert (first.data["status"], first.data["reused"], first.data["open_questions"]) == (
        "generating", False, None,
    )  # fmt: skip
    second = await call("start_interview", {"batch_id": b})
    assert second.data["interview_id"] == first.data["interview_id"] and second.data["reused"]
    assert second.data["card_refs"] != first.data["card_refs"]
    assert len(w.job_rows("generate_interview")) == 1
    generate_interview(w.ctx, first.data["interview_id"], model_factory=lambda: RecordedModel(w))
    ready = await call("start_interview", {"batch_id": b})
    assert (ready.data["interview_id"], ready.data["status"], ready.data["open_questions"]) == (
        first.data["interview_id"], "ready", 5,
    )  # fmt: skip
    for q in w.questions(first.data["interview_id"]):
        answers.skip(w.ctx, q["id"])
    fresh = await call("start_interview", {"batch_id": b})
    assert not fresh.data["reused"] and len(w.job_rows("generate_interview")) == 2
    kinds = [(c.tool, c.kind, c.subject) for c in cards()]
    assert kinds[0] == ("start_interview", "interview",
                        {"interview_id": first.data["interview_id"]})  # fmt: skip
    assert len(kinds) == 4


async def test_start_interview_scope_arguments():
    w = World()
    b = w.batch()
    w.cluster(b)
    none = await call("start_interview", {})
    two = await call("start_interview", {"queue": True, "batch_id": b})
    assert none.data["error"]["code"] == two.data["error"]["code"] == "invalid_argument"
    by_name = await call("start_interview", {"counterparty": "Hello bank", "lang": "fr"})
    assert not by_name.is_error, by_name.text
    iv = w.row("interviews", by_name.data["interview_id"])
    assert iv["kind"] == "on_demand" and iv["lang"] == "fr"
    assert len(iv["scope"]["candidate_document_ids"]) == 3
    unknown = await call("start_interview", {"counterparty": "Nobody at all"})
    assert unknown.data["error"]["field"] == "counterparty"


async def test_start_interview_takes_the_attributed_web_turn_language():
    w = World()
    w.cluster(w.batch())
    rows.turn(reply_language="ro")
    res = await call("start_interview", {"queue": True})
    assert w.row("interviews", res.data["interview_id"])["lang"] == "ro"
    [card] = cards()
    assert card.turn_id is not None
    tg = await call("start_interview", {"queue": True}, channel="telegram")
    assert tg.data["reused"] and cards()[-1].turn_id is None


async def test_answer_question_depends_gives_two_drafts_two_previews_two_cards():
    w = World()
    interview_id, qid = agipi_only(w)
    res = await call("answer_question", {"question_id": qid, "option_id": "a"})
    assert not res.is_error, res.text
    assert [r["state"] for r in res.data["rules"]] == ["draft", "draft"]
    assert len(res.data["previews"]) == 2
    assert all(len(p["moves"]) <= 2 for p in res.data["previews"])
    assert [(c.tool, c.kind) for c in cards()] == [("answer_question", "rulePreview")] * 2
    assert [c.subject["rule_id"] for c in cards()] == [r["id"] for r in res.data["rules"]]
    r = T["rules"]
    with w.engine.connect() as conn:
        origins = (
            conn.execute(
                select(r.c.origin_question_id).where(
                    r.c.id.in_([x["id"] for x in res.data["rules"]])
                )
            )
            .scalars()
            .all()
        )
    assert origins == [qid, qid]
    f = T["file_ops"]
    with w.engine.connect() as conn:
        created = conn.execute(select(f.c.actor, f.c.via).where(f.c.action == "rule.create")).all()
    assert created == [("mona", "chat"), ("mona", "chat")]
    again = await call("answer_question", {"question_id": qid, "option_id": "a"})
    assert [x["id"] for x in again.data["rules"]] == [x["id"] for x in res.data["rules"]]
    other = await call("answer_question", {"question_id": qid, "option_id": "b"})
    assert other.data["error"]["code"] == "conflict"
    assert other.data["error"]["hint"] == "Already answered with option 'a'."


async def test_answer_question_ask_is_one_active_rule_without_preview_or_card():
    w = World()
    interview_id, qid = agipi_only(w)
    q = w.row("interview_questions", qid)
    ask = next(o["id"] for o in q["options"] if o["rule_draft"]["kind"] == "ask")
    res = await call("answer_question", {"question_id": qid, "option_id": ask})
    assert [r["state"] for r in res.data["rules"]] == ["active"]
    assert res.data["previews"] == [] and res.data["card_refs"] == [] and cards() == []
    both = await call("answer_question", {"question_id": qid, "option_id": "a", "free_text": "x"})
    assert both.data["error"]["code"] == "invalid_argument"

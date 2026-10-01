import asyncio
import json

import httpx
import pytest
from sqlalchemy import insert

from mona.chat import notes as chat_notes
from mona.chat import stream as chat_stream
from mona.db import get_engine
from mona.db.models import CardActionNote
from mona.ids import new_id
from tests import rows
from tests.api_client import api_client
from tests.fixtures import S1_OVERLAY_STREAM
from tests.hermes_fake import (
    BODY,
    FakeHermes,
    app_with,
    chunk,
    meta,
    parse,
    post_chat,
    sse_body,
    types,
)
from tests.mcp_http import call

pytestmark = pytest.mark.usefixtures("clean")

S1 = S1_OVERLAY_STREAM.read_bytes()
FRAMING = ["start", "start-step"]
OFFLINE = ["start", "start-step", "error", "finish-step", "finish", "[DONE]"]


def upstream_system(fake: FakeHermes) -> str:
    req = next(r for r in fake.requests if r.url.path == "/v1/chat/completions")
    return json.loads(req.content)["messages"][0]["content"]


AGENT_FAILURE = [
    chunk({"role": "assistant"}),
    ": keepalive",
    "",
    chunk(
        {},
        finish="error",
        error={"message": "model endpoint down"},
        hermes={"error_code": "agent_error"},
    ),
    "data: [DONE]",
]


async def test_turn_streams_parts_and_emits_the_tool_card_after_its_completion():
    doc = rows.document("URSSAF appel de cotisation T3", counterparty="opco", amount=1284.0)
    fake = FakeHermes(S1, during_stream=lambda: call("get_document", {"document_id": doc}))
    res, chunks = await post_chat(fake)
    assert res.headers["x-vercel-ai-ui-message-stream"] == "v1"
    assert res.headers["content-type"].startswith("text/event-stream")
    assert res.headers["cache-control"] == "no-cache"
    assert res.headers["x-accel-buffering"] == "no"
    t = types(chunks)
    assert t[:3] == ["start", "start-step", "reasoning-start"]
    assert t[-3:] == ["finish-step", "finish", "[DONE]"]
    out = t.index("tool-output-available")
    assert t[out + 1] == "data-doc" and t.count("data-doc") == 1
    card = chunks[out + 1]
    assert card["id"] == doc and card["data"]["title"] == "URSSAF appel de cotisation T3"
    assert card["data"]["amount"] == {"value": 1284.0, "currency": "EUR"}
    m = meta(chunks)
    assert m["conversationId"].startswith("cnv_") and m["replyLanguage"] == "en"
    assert chunks[-2]["finishReason"] == "stop"
    assert chunks[-2]["messageMetadata"]["reasoningMs"] >= 0
    turn = rows.turn_row(m["turnId"])
    assert (turn.status, turn.finish_reason, turn.user_text) == ("closed", "stop", BODY["message"])
    assert turn.ui_message_id == chunks[0]["messageId"]
    assert turn.usage["prompt_tokens"] == 15830
    (card_row,) = rows.card_rows()
    assert card_row.turn_id == m["turnId"] and card_row.emitted_at is not None

    upstream = next(r for r in fake.requests if r.url.path == "/v1/chat/completions")
    body = json.loads(upstream.content)
    assert upstream.headers["x-hermes-session-id"] == m["conversationId"]
    assert upstream.headers["authorization"] == "Bearer key"
    assert (body["model"], body["stream"]) == ("mona", True)
    assert [m_["role"] for m_ in body["messages"]] == ["system", "user"]
    assert body["messages"][1]["content"] == BODY["message"]
    system = body["messages"][0]["content"]
    assert "- Page: /documents/doc_x — Document viewer" in system
    assert system.endswith("- The person wrote in English. Reply in English.")


async def test_turn_stores_the_streamed_parts():
    doc = rows.document("URSSAF appel", counterparty="opco")
    fake = FakeHermes(S1, during_stream=lambda: call("get_document", {"document_id": doc}))
    _, chunks = await post_chat(fake)
    parts = rows.turn_row(meta(chunks)["turnId"]).parts
    assert [p["type"] for p in parts] == ["reasoning", "tool", "data", "reasoning", "text"]
    assert parts[1] == {
        "type": "tool",
        "tool_call_id": "chatcmpl-tool-8e55056018ba2970",
        "tool_name": "get_document",
        "completed": True,
    }
    assert parts[2] == {"type": "data", "kind": "doc", "id": doc}
    text = "".join(c["delta"] for c in chunks if c != "[DONE]" and c["type"] == "text-delta")
    assert parts[4]["text"] == text


async def test_request_validation_is_400_and_unknown_conversation_is_404():
    fake = FakeHermes(S1)
    res, _ = await post_chat(fake, message="   ")
    assert res.status_code == 400 and res.json()["error"]["code"] == "invalid_request"
    res, _ = await post_chat(fake, message="x" * 4001)
    assert res.status_code == 400
    res, _ = await post_chat(fake, pageContext={"route": "/x" * 101, "summary": "s"})
    assert res.status_code == 400
    res, _ = await post_chat(fake, locale="de")
    assert res.status_code == 400
    res, _ = await post_chat(fake, conversationId="cnv_" + "0" * 26)
    assert res.status_code == 404 and res.json()["error"]["code"] == "not_found"
    assert fake.requests == []


async def test_a_body_over_32_kib_is_refused():
    transport = httpx.ASGITransport(app=app_with(FakeHermes(S1)))
    async with api_client(transport) as c:
        res = await c.post(
            "/api/chat",
            content=json.dumps({**BODY, "padding": "x" * 33_000}),
            headers={"content-type": "application/json"},
        )
    assert res.status_code == 400 and res.json()["error"]["code"] == "invalid_request"


async def test_a_chunked_body_over_32_kib_is_refused():
    async def chunks():
        yield json.dumps(BODY)[:-1].encode() + b', "padding": "'
        for _ in range(40):
            yield b"x" * 1024
        yield b'"}'

    transport = httpx.ASGITransport(app=app_with(FakeHermes(S1)))
    async with api_client(transport) as c:
        res = await c.post(
            "/api/chat", content=chunks(), headers={"content-type": "application/json"}
        )
    assert "content-length" not in res.request.headers
    assert res.status_code == 400 and res.json()["error"]["code"] == "invalid_request"


async def test_reply_language_request_overrides_a_french_message_and_is_pinned():
    fake = FakeHermes(S1)
    _, chunks = await post_chat(
        fake, message="Combien avons-nous payé à l'URSSAF ?", replyLanguage="en"
    )
    assert meta(chunks)["replyLanguage"] == "en"
    system = upstream_system(fake)
    assert system.endswith("- The person asked for replies in English. Reply in English.")
    fake = FakeHermes(S1)
    _, chunks = await post_chat(fake, message="Combien avons-nous payé à l'URSSAF ?")
    assert meta(chunks)["replyLanguage"] == "fr"


async def test_undetected_language_falls_back_to_the_previous_turn_then_the_locale():
    cid, _ = rows.turn(status="closed", reply_language="ro")
    _, chunks = await post_chat(FakeHermes(S1), conversationId=cid, message="OK")
    assert meta(chunks)["replyLanguage"] == "ro"
    _, chunks = await post_chat(FakeHermes(S1), message="OK", locale="fr")
    assert meta(chunks)["replyLanguage"] == "fr"


# Session identity (C3 §8.12)


async def test_new_conversation_row_is_written_before_hermes_and_names_the_session():
    seen = []

    def on_session(body):
        seen.append((body, rows.one("SELECT id FROM conversations WHERE id = %s", (body["id"],))))

    fake = FakeHermes(S1, on_session=on_session)
    _, chunks = await post_chat(fake)
    cid = meta(chunks)["conversationId"]
    assert fake.paths()[0] == "/api/sessions"
    assert seen == [({"id": cid, "title": cid}, (cid,))]
    assert (
        rows.one("SELECT title FROM conversations WHERE id = %s", (cid,)).title == BODY["message"]
    )


async def test_session_exists_is_success_and_same_first_message_twice_works():
    fake = FakeHermes(S1, session_status=409)
    _, first = await post_chat(fake)
    _, second = await post_chat(fake)
    assert types(first)[-1] == types(second)[-1] == "[DONE]"
    assert first[-2]["finishReason"] == second[-2]["finishReason"] == "stop"
    assert meta(first)["conversationId"] != meta(second)["conversationId"]


async def test_a_later_turn_skips_session_creation_once_a_turn_closed():
    fake = FakeHermes(S1)
    _, chunks = await post_chat(fake)
    await post_chat(fake, conversationId=meta(chunks)["conversationId"])
    assert fake.paths().count("/api/sessions") == 1


async def test_hermes_down_fails_the_first_turn_then_the_next_creates_the_session():
    _, chunks = await post_chat(FakeHermes(S1, down={"/api/sessions"}))
    assert types(chunks) == OFFLINE and chunks[2]["errorText"] == "mona_offline"
    assert chunks[4]["finishReason"] == "error"
    m = meta(chunks)
    turn = rows.turn_row(m["turnId"])
    assert (turn.status, turn.error_code) == ("failed", "hermes_unreachable")
    fake = FakeHermes(S1)
    _, chunks = await post_chat(fake, conversationId=m["conversationId"])
    assert fake.paths()[0] == "/api/sessions" and chunks[-2]["finishReason"] == "stop"


async def test_session_creation_refused_is_mona_offline_with_the_status():
    _, chunks = await post_chat(FakeHermes(S1, session_status=400))
    assert types(chunks) == OFFLINE
    assert rows.turn_row(meta(chunks)["turnId"]).error_code == "hermes_http_400"


# Errors (C3 §8.8)


async def test_hermes_unreachable_on_an_existing_conversation_is_mona_offline():
    cid, _ = rows.turn(status="closed")
    rows.note(cid, "Applied the rule.")
    _, chunks = await post_chat(FakeHermes(S1, down={"/v1/chat"}), conversationId=cid)
    assert types(chunks) == OFFLINE
    turn = rows.turn_row(meta(chunks)["turnId"])
    assert (turn.status, turn.error_code) == ("failed", "hermes_unreachable")
    assert [n.consumed_turn_id for n in rows.notes_of(cid)] == [None]


async def test_upstream_http_error_before_any_chunk_is_mona_offline():
    cid, _ = rows.turn(status="closed")

    class Refusing(FakeHermes):
        async def __call__(self, request):
            if request.url.path == "/v1/chat/completions":
                return httpx.Response(503)
            return await super().__call__(request)

    _, chunks = await post_chat(Refusing(), conversationId=cid)
    assert types(chunks) == OFFLINE
    assert rows.turn_row(meta(chunks)["turnId"]).error_code == "hermes_http_503"


async def test_first_byte_timeout_is_mona_offline(monkeypatch):
    monkeypatch.setattr(chat_stream, "FIRST_BYTE_S", 0.2)
    cid, _ = rows.turn(status="closed")

    async def never() -> bytes:
        await asyncio.sleep(5)
        return b""

    _, chunks = await post_chat(FakeHermes(never), conversationId=cid)
    assert types(chunks) == OFFLINE
    assert rows.turn_row(meta(chunks)["turnId"]).error_code == "hermes_unreachable"


async def test_upstream_cut_mid_stream_is_stream_interrupted_and_notes_stay_consumed():
    cid, _ = rows.turn(status="closed")
    rows.note(cid, "Applied the rule.")
    cut = b"\n".join(S1.split(b"\n")[:50]) + b"\n"
    _, chunks = await post_chat(FakeHermes(cut), conversationId=cid)
    t = types(chunks)
    assert t[-4:] == ["reasoning-end", "error", "finish", "[DONE]"]
    assert chunks[-3]["errorText"] == "stream_interrupted"
    turn_id = meta(chunks)["turnId"]
    assert rows.turn_row(turn_id).error_code == "stream_interrupted"
    assert [n.consumed_turn_id for n in rows.notes_of(cid)] == [turn_id]


async def test_unparseable_upstream_chunk_is_stream_interrupted():
    cid, _ = rows.turn(status="closed")
    body = sse_body([chunk({"content": "Hello"}), "data: {not json", "data: [DONE]"])
    _, chunks = await post_chat(FakeHermes(body), conversationId=cid)
    assert types(chunks)[-5:] == ["text-delta", "text-end", "error", "finish", "[DONE]"]
    assert chunks[-3]["errorText"] == "stream_interrupted"


async def test_idle_timeout_mid_stream_is_stream_interrupted(monkeypatch):
    monkeypatch.setattr(chat_stream, "IDLE_S", 0.2)
    cid, _ = rows.turn(status="closed")

    class Stalling(FakeHermes):
        async def __call__(self, request):
            if request.url.path != "/v1/chat/completions":
                return await super().__call__(request)

            async def body():
                yield (chunk({"content": "Hel"}) + "\n\n").encode()
                await asyncio.sleep(5)

            return httpx.Response(200, content=body())

    _, chunks = await post_chat(Stalling(), conversationId=cid)
    assert types(chunks)[-3:] == ["error", "finish", "[DONE]"]
    assert chunks[-3]["errorText"] == "stream_interrupted"
    assert rows.turn_row(meta(chunks)["turnId"]).error_code == "stream_interrupted"


async def test_in_band_agent_failure_before_text_is_mona_offline_and_releases_notes():
    cid, _ = rows.turn(status="closed")
    rows.note(cid, "Applied the rule.")
    _, chunks = await post_chat(FakeHermes(sse_body(AGENT_FAILURE)), conversationId=cid)
    assert types(chunks) == OFFLINE
    assert chunks[2]["errorText"] == "mona_offline" and chunks[4]["finishReason"] == "error"
    turn = rows.turn_row(meta(chunks)["turnId"])
    assert (turn.status, turn.error_code, turn.finish_reason) == (
        "failed",
        "hermes_agent_error",
        "error",
    )
    assert [n.consumed_turn_id for n in rows.notes_of(cid)] == [None]


async def test_in_band_agent_failure_after_text_is_stream_interrupted():
    cid, _ = rows.turn(status="closed")
    rows.note(cid, "Applied the rule.")
    body = sse_body([chunk({"content": "Let me check"}), *AGENT_FAILURE])
    _, chunks = await post_chat(FakeHermes(body), conversationId=cid)
    assert types(chunks) == [
        *FRAMING,
        "text-start",
        "text-delta",
        "text-end",
        "error",
        "finish",
        "[DONE]",
    ]
    assert chunks[-3]["errorText"] == "stream_interrupted"
    turn_id = meta(chunks)["turnId"]
    assert rows.turn_row(turn_id).error_code == "hermes_agent_error"
    assert [n.consumed_turn_id for n in rows.notes_of(cid)] == [turn_id]


async def test_adapter_failure_mid_stream_reports_internal_and_fails_the_turn(monkeypatch):
    async def broken(*_):
        raise RuntimeError("db down")

    monkeypatch.setattr("mona.chat.cards.emit_pending", broken)
    cid, _ = rows.turn(status="closed")
    _, chunks = await post_chat(FakeHermes(S1), conversationId=cid)
    t = types(chunks)
    assert t[-4:] == ["tool-output-available", "error", "finish", "[DONE]"]
    assert chunks[-3]["errorText"] == "internal"
    assert rows.turn_row(meta(chunks)["turnId"]).error_code == "internal"


async def test_upstream_keepalives_are_forwarded():
    cid, _ = rows.turn(status="closed")
    body = sse_body(
        [": keepalive", "", chunk({"content": "Hi"}), chunk({}, "stop"), "data: [DONE]"]
    )
    transport = httpx.ASGITransport(app=app_with(FakeHermes(body)))
    async with api_client(transport) as c:
        res = await c.post("/api/chat", json={**BODY, "conversationId": cid})
    assert ": keepalive\n\n" in res.text
    assert types(parse(res.text))[-3:] == ["finish-step", "finish", "[DONE]"]


async def test_adapter_writes_its_own_keepalive_while_upstream_is_silent(monkeypatch):
    monkeypatch.setattr(chat_stream, "KEEPALIVE_S", 0.05)
    cid, _ = rows.turn(status="closed")

    async def slow() -> bytes:
        await asyncio.sleep(0.3)
        return sse_body([chunk({"content": "Hi"}), chunk({}, "stop"), "data: [DONE]"])

    transport = httpx.ASGITransport(app=app_with(FakeHermes(slow)))
    async with api_client(transport) as c:
        res = await c.post("/api/chat", json={**BODY, "conversationId": cid})
    assert res.text.count(": keepalive\n\n") >= 2


# Lease (C3 §8.9) and notes


async def test_two_concurrent_posts_on_one_conversation_give_one_stream_and_one_409():
    cid, _ = rows.turn(status="closed")
    released = asyncio.Event()

    async def gated() -> bytes:
        await released.wait()
        return S1

    app = app_with(FakeHermes(gated))

    async def post():
        transport = httpx.ASGITransport(app=app)
        async with api_client(transport) as c:
            try:
                return await c.post("/api/chat", json={**BODY, "conversationId": cid})
            finally:
                released.set()

    a, b = await asyncio.gather(post(), post())
    assert sorted([a.status_code, b.status_code]) == [200, 409]
    refused = a if a.status_code == 409 else b
    assert refused.json()["error"]["code"] == "turn_in_progress"
    assert (
        rows.one(
            "SELECT count(*) AS n FROM chat_turns WHERE conversation_id = %s AND status = 'closed'",
            (cid,),
        ).n
        == 2
    )


async def test_expired_open_turn_is_failed_and_a_new_turn_opens():
    cid, stale = rows.turn(status="open", expires_in_s=-1)
    res, chunks = await post_chat(FakeHermes(S1), conversationId=cid)
    assert res.status_code == 200 and types(chunks)[-1] == "[DONE]"
    turn = rows.turn_row(stale)
    assert (turn.status, turn.error_code) == ("failed", "lease_expired")
    assert turn.closed_at is not None


async def test_a_live_open_turn_is_409():
    cid, _ = rows.turn(status="open")
    res, _ = await post_chat(FakeHermes(S1), conversationId=cid)
    assert res.status_code == 409 and res.json()["error"]["code"] == "turn_in_progress"


async def test_pending_notes_are_consumed_by_the_turn_and_listed_in_the_overlay():
    cid, _ = rows.turn(status="closed")
    for i in range(1, 13):
        rows.note(cid, f"Note {i}.")
    fake = FakeHermes(S1)
    _, chunks = await post_chat(fake, conversationId=cid)
    turn_id = meta(chunks)["turnId"]
    assert {n.consumed_turn_id for n in rows.notes_of(cid)} == {turn_id}
    lines = upstream_system(fake).splitlines()
    assert lines[5:] == [f"- Note {i}." for i in range(3, 13)] + ["- (and 2 earlier actions)"]
    fake = FakeHermes(S1)
    await post_chat(fake, conversationId=cid)
    assert "Card actions" not in upstream_system(fake)


async def test_notes_are_consumed_in_the_lease_transaction():
    cid, _ = rows.turn(status="open")
    rows.note(cid, "Applied the rule.")
    res, _ = await post_chat(FakeHermes(S1), conversationId=cid)
    assert res.status_code == 409
    assert [n.consumed_turn_id for n in rows.notes_of(cid)] == [None]


async def test_notes_written_in_one_transaction_keep_their_write_order():
    cid, tid = rows.turn(status="closed")
    written = [f"Note {i}." for i in range(30)]
    async with get_engine().begin() as conn:
        for text in written:
            await chat_notes.add_note(conn, cid, "rule.apply", text)
    stored = rows.all_rows(
        "SELECT created_at FROM card_action_notes WHERE conversation_id = %s", (cid,)
    )
    assert len({r.created_at for r in stored}) == 1
    assert [n.text for n in rows.notes_of(cid)] == written
    async with get_engine().begin() as conn:
        assert await chat_notes.consume(conn, cid, tid) == written


async def test_consume_orders_notes_by_id_not_by_storage_order():
    cid, tid = rows.turn(status="closed")
    ids = sorted(new_id("not") for _ in range(30))
    async with get_engine().begin() as conn:
        for i in reversed(range(30)):
            await conn.execute(
                insert(CardActionNote).values(
                    id=ids[i], conversation_id=cid, kind="rule.apply", text=f"Note {i}."
                )
            )
    async with get_engine().begin() as conn:
        assert await chat_notes.consume(conn, cid, tid) == [f"Note {i}." for i in range(30)]


async def test_lease_is_extended_while_upstream_events_arrive(monkeypatch):
    monkeypatch.setattr(chat_stream, "LEASE_TOUCH_S", 0.0)
    cid, _ = rows.turn(status="closed")
    touched = []
    real = chat_stream.touch

    async def spy(engine, turn):
        await real(engine, turn)
        touched.append(rows.turn_row(turn.id).lease_expires_at)

    monkeypatch.setattr(chat_stream, "touch", spy)
    await post_chat(FakeHermes(S1), conversationId=cid)
    assert len(touched) > 10 and touched == sorted(touched)


# Conversations (C3 §7.1)


async def test_conversation_list_is_newest_first_with_turn_counts():
    old, _ = rows.turn(status="closed")
    rows.turn(old, status="closed")
    fake = FakeHermes(S1)
    _, chunks = await post_chat(fake, message="How much did we pay AGIPI last year?")
    transport = httpx.ASGITransport(app=app_with(fake))
    async with api_client(transport) as c:
        feed = (await c.get("/api/conversations")).json()
        page1 = (await c.get("/api/conversations", params={"limit": 1})).json()
        page2 = (
            await c.get("/api/conversations", params={"limit": 1, "cursor": page1["nextCursor"]})
        ).json()
        found = (await c.get("/api/conversations", params={"q": "agipi"})).json()
        reused = await c.get("/api/conversations", params={"q": "x", "cursor": page1["nextCursor"]})
    listed = feed["items"]
    assert feed["nextCursor"] is None
    assert [page1["items"][0]["id"], page2["items"][0]["id"]] == [listed[0]["id"], listed[1]["id"]]
    assert [i["id"] for i in found["items"]] == [listed[0]["id"]]
    assert reused.status_code == 400 and reused.json()["error"]["field"] == "cursor"
    assert listed[0] == {
        "id": meta(chunks)["conversationId"],
        "title": "How much did we pay AGIPI last year?",
        "lastMessageAt": listed[0]["lastMessageAt"],
        "turnCount": 1,
    }
    assert listed[0]["lastMessageAt"].endswith("Z")
    assert (listed[1]["id"], listed[1]["turnCount"]) == (old, 2)

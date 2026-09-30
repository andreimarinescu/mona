import json

import httpx
import pytest

from mona.app import create_app
from mona.chat.hermes import HermesClient, get_hermes
from mona.spike import mcp as spike_mcp
from tests.fixtures import S1_OVERLAY_STREAM, S5_SESSION_MESSAGES
from tests.spike_rows import add_turn, card_rows, turn_row

pytestmark = pytest.mark.usefixtures("clean_spike")

BODY = {
    "message": "What am I looking at?",
    "pageContext": {"route": "/documents/doc_urssaf_q3", "summary": "Document viewer"},
    "locale": "en",
}


def tool_message(ref: str) -> dict:
    wrapped = json.dumps({"result": json.dumps({"card_refs": [ref]})})
    return {
        "role": "tool",
        "content": f'<untrusted_tool_result source="x">\n{wrapped}\n</untrusted>',
    }


class FakeHermes:
    """Stands in for the Hermes API server; `during_stream` runs as the MCP tools would."""

    def __init__(self, during_stream=None, messages=None, fail=None):
        self.during_stream = during_stream
        self.messages = messages
        self.fail = fail
        self.requests: list[httpx.Request] = []
        self.titles: list[str] = []

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.fail and request.url.path in self.fail:
            raise httpx.ConnectError("down", request=request)
        if request.url.path == "/api/sessions":
            self.titles.append(json.loads(request.content)["title"])
            return httpx.Response(200, json={"session": {"id": "sess-1"}})
        if request.url.path == "/v1/chat/completions":
            if self.during_stream:
                await self.during_stream()
            return httpx.Response(200, content=S1_OVERLAY_STREAM.read_bytes())
        if request.url.path.endswith("/messages"):
            msgs = self.messages() if callable(self.messages) else self.messages or []
            return httpx.Response(200, json={"object": "list", "data": msgs})
        return httpx.Response(404)


async def post_chat(fake: FakeHermes, body=BODY):
    app = create_app()
    app.dependency_overrides[get_hermes] = lambda: HermesClient(
        "http://hermes", "key", transport=httpx.MockTransport(fake)
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        res = await c.post("/api/chat", json=body)
    return res, parse(res.text) if res.status_code == 200 else None


def parse(text: str) -> list:
    out = []
    for frame in text.split("\n\n"):
        if frame.startswith("data: "):
            body = frame[6:]
            out.append(body if body == "[DONE]" else json.loads(body))
    return out


def types(chunks):
    return [c if c == "[DONE]" else c["type"] for c in chunks]


async def test_turn_streams_parts_and_emits_the_tool_card_after_its_completion():
    fake = FakeHermes(
        during_stream=lambda: spike_mcp.get_document("doc_urssaf_q3"),
        messages=lambda: [{"role": "user", "content": "x"}, tool_message(card_rows()[0].id)],
    )
    res, chunks = await post_chat(fake)
    assert res.headers["x-vercel-ai-ui-message-stream"] == "v1"
    assert res.headers["content-type"].startswith("text/event-stream")
    t = types(chunks)
    assert t[:3] == ["start", "start-step", "reasoning-start"]
    assert t[-3:] == ["finish-step", "finish", "[DONE]"]
    out = t.index("tool-output-available")
    assert t[out + 1] == "data-doc" and t.count("data-doc") == 1
    card = chunks[out + 1]
    assert (
        card["id"] == "doc_urssaf_q3" and card["data"]["title"] == "URSSAF appel de cotisation T3"
    )
    start = chunks[0]
    turn_id = start["messageMetadata"]["turnId"]
    assert start["messageMetadata"]["conversationId"].startswith("cnv_")
    assert fake.titles == [start["messageMetadata"]["conversationId"]]
    assert chunks[-2]["finishReason"] == "stop"
    assert turn_row(turn_id).status == "closed"
    assert card_rows()[0].emitted_at is not None

    upstream = json.loads(fake.requests[1].content)
    assert fake.requests[1].headers["x-hermes-session-id"] == "sess-1"
    assert upstream["stream"] is True
    assert [m["role"] for m in upstream["messages"]] == ["system", "user"]
    assert (
        "- Page: /documents/doc_urssaf_q3 — Document viewer" in upstream["messages"][0]["content"]
    )
    assert "Reply in English." in upstream["messages"][0]["content"]


async def test_finish_reconciles_unattributed_cards_and_drops_strays():
    async def tools():
        await spike_mcp.record_cards(
            "get_document", [("doc", {"document_id": "doc_edf_sept"})], "telegram"
        )
        await spike_mcp.search_documents("AGIPI")

    def messages():
        unattributed = next(r for r in card_rows() if r.subject["document_id"] == "doc_edf_sept")
        return [{"role": "user", "content": "x"}, tool_message(unattributed.id)]

    res, chunks = await post_chat(FakeHermes(during_stream=tools, messages=messages))
    cards = [c for c in chunks if c != "[DONE]" and c["type"] == "data-doc"]
    assert [c["id"] for c in cards] == ["doc_edf_sept"]
    rows = {r.subject["document_id"]: r for r in card_rows()}
    turn_id = chunks[0]["messageMetadata"]["turnId"]
    assert rows["doc_edf_sept"].turn_id == turn_id
    assert rows["doc_agipi_per"].turn_id is None and rows["doc_agipi_per"].emitted_at is None


async def test_hermes_unreachable_on_an_existing_conversation_is_mona_offline():
    cid, earlier = add_turn(status="closed")
    res, chunks = await post_chat(
        FakeHermes(fail={"/v1/chat/completions"}), {**BODY, "conversationId": cid}
    )
    assert types(chunks) == ["start", "start-step", "error", "finish-step", "finish", "[DONE]"]
    assert chunks[2]["errorText"] == "mona_offline" and chunks[4]["finishReason"] == "error"
    turn_id = chunks[0]["messageMetadata"]["turnId"]
    assert (turn_row(turn_id).status, turn_row(turn_id).error_code) == (
        "failed",
        "hermes_unreachable",
    )


async def test_hermes_unreachable_for_a_new_conversation_is_mona_offline():
    res, chunks = await post_chat(FakeHermes(fail={"/api/sessions"}))
    assert types(chunks) == ["start", "start-step", "error", "finish-step", "finish", "[DONE]"]
    assert chunks[2]["errorText"] == "mona_offline"


async def test_upstream_cut_mid_stream_is_stream_interrupted():
    cid, _ = add_turn(status="closed")
    lines = S1_OVERLAY_STREAM.read_bytes().split(b"\n")
    cut = b"\n".join(lines[:50]) + b"\n"

    class Cut(FakeHermes):
        async def __call__(self, request):
            if request.url.path == "/v1/chat/completions":
                return httpx.Response(200, content=cut)
            return await super().__call__(request)

    res, chunks = await post_chat(Cut(), {**BODY, "conversationId": cid})
    t = types(chunks)
    assert t[-4:] == ["reasoning-end", "error", "finish", "[DONE]"]
    assert chunks[-3]["errorText"] == "stream_interrupted"
    assert turn_row(chunks[0]["messageMetadata"]["turnId"]).error_code == "stream_interrupted"


async def test_a_second_turn_while_one_is_open_is_409_and_unknown_conversation_is_404():
    cid, _ = add_turn(status="open")
    res, _ = await post_chat(FakeHermes(), {**BODY, "conversationId": cid})
    assert res.status_code == 409 and res.json()["detail"]["code"] == "turn_in_progress"
    res, _ = await post_chat(FakeHermes(), {**BODY, "conversationId": "cnv_missing"})
    assert res.status_code == 404


async def test_expired_open_turn_is_failed_and_a_new_turn_opens():
    cid, stale = add_turn(status="open", expires_in_s=-1)
    res, chunks = await post_chat(FakeHermes(), {**BODY, "conversationId": cid})
    assert res.status_code == 200 and types(chunks)[-1] == "[DONE]"
    assert (turn_row(stale).status, turn_row(stale).error_code) == ("failed", "lease_expired")


async def test_transcript_reload_rebuilds_parts_and_cards_with_the_streamed_ids():
    fake = FakeHermes(
        during_stream=lambda: spike_mcp.get_document("doc_urssaf_q3"),
        messages=lambda: [{"role": "user", "content": "x"}, tool_message(card_rows()[0].id)],
    )
    _, chunks = await post_chat(fake)
    start = chunks[0]
    cid = start["messageMetadata"]["conversationId"]
    ref = card_rows()[0].id
    fixture = json.loads(S5_SESSION_MESSAGES.read_text())["data"]
    history = [
        {**m, "content": m["content"].replace("crd_01m3sg4601h7fp4ffxx3enfd3d", ref)}
        for m in fixture
    ]
    app = create_app()
    app.dependency_overrides[get_hermes] = lambda: HermesClient(
        "http://hermes", "key", transport=httpx.MockTransport(FakeHermes(messages=history))
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        msgs = (await c.get(f"/api/conversations/{cid}/messages")).json()
    user, assistant = msgs
    assert user["id"] == f"{start['messageMetadata']['turnId']}:u"
    assert user["parts"] == [{"type": "text", "text": "Find the URSSAF letter"}]
    assert assistant["id"] == start["messageId"]
    assert [p["type"] for p in assistant["parts"]] == [
        "reasoning",
        "dynamic-tool",
        "reasoning",
        "dynamic-tool",
        "data-doc",
        "reasoning",
        "text",
    ]
    tool = assistant["parts"][1]
    assert (tool["toolName"], tool["input"], tool["state"]) == (
        "search_documents",
        {"query": "URSSAF"},
        "output-available",
    )
    assert assistant["parts"][4]["id"] == "doc_urssaf_q3"


async def test_adapter_failure_mid_stream_reports_internal_and_fails_the_turn(monkeypatch):
    async def broken(*_):
        raise RuntimeError("db down")

    monkeypatch.setattr("mona.chat.cards.emit_pending", broken)
    cid, _ = add_turn(status="closed")
    _, chunks = await post_chat(FakeHermes(), {**BODY, "conversationId": cid})
    t = types(chunks)
    assert t[t.index("tool-output-available") - 1] == "tool-input-available"
    assert t[-4:] == ["tool-output-available", "error", "finish", "[DONE]"]
    assert chunks[-3]["errorText"] == "internal"
    assert turn_row(chunks[0]["messageMetadata"]["turnId"]).error_code == "internal"

import asyncio

import httpx
import pytest

from mona.chat.stream import run_turn
from mona.chat.turns import open_turn
from mona.db import get_engine
from tests import rows
from tests.api_client import api_client
from tests.fixtures import S5_TWO_TOOLS_STREAM
from tests.hermes_fake import FakeHermes, app_with, chunk, meta, parse, post_chat, tool_event
from tests.mcp_http import call

pytestmark = pytest.mark.usefixtures("clean")


def deltas(chunks, kind: str, part_id: str) -> str:
    return "".join(
        c["delta"]
        for c in chunks
        if c != "[DONE]" and c["type"] == f"{kind}-delta" and c["id"] == part_id
    )


class NoHermes(FakeHermes):
    async def __call__(self, request):
        self.requests.append(request)
        raise AssertionError(f"Hermes called: {request.url}")


async def closed_turn(cid: str | None, search_doc: str, open_doc: str) -> list:
    async def tools():
        await call("search_documents", {"query": "URSSAF"})
        await call("get_document", {"document_id": open_doc})

    fake = FakeHermes(S5_TWO_TOOLS_STREAM.read_bytes(), during_stream=tools)
    body = {"message": "Find the URSSAF letter"}
    if cid:
        body["conversationId"] = cid
    _, chunks = await post_chat(fake, body)
    return chunks


async def aborted_turn(cid: str) -> list:
    """Streams reasoning, a running tool and some text, then the client goes away."""
    turn = await open_turn(get_engine(), cid, "And the EDF bill?", "en", None)
    gate = asyncio.Event()

    class Hanging(FakeHermes):
        async def __call__(self, request):
            if request.url.path != "/v1/chat/completions":
                return await super().__call__(request)

            async def body():
                for line in [
                    chunk({"reasoning_content": "Let me look"}),
                    *tool_event("get_document", "c9", "running"),
                    chunk({"content": "Looking"}),
                ]:
                    yield (line + "\n").encode()
                gate.set()
                await asyncio.sleep(30)

            return httpx.Response(200, content=body())

    seen: list = []
    texted = asyncio.Event()

    async def consume():
        async for frame in run_turn(get_engine(), Hanging().client(), turn, "/chat", "Chat page"):
            seen.extend(parse(frame))
            if any(c != "[DONE]" and c["type"] == "text-delta" for c in seen):
                texted.set()

    task = asyncio.create_task(consume())
    await asyncio.wait_for(gate.wait(), 5)
    await asyncio.wait_for(texted.wait(), 5)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    return seen


async def test_reload_rebuilds_closed_aborted_and_offline_turns_without_hermes():
    search_doc = rows.document("URSSAF appel de cotisation T3", counterparty="opco", amount=1284.0)
    open_doc = rows.document("EDF facture septembre", amount=96.5)
    first = await closed_turn(None, search_doc, open_doc)
    cid = meta(first)["conversationId"]
    aborted = await aborted_turn(cid)
    _, offline = await post_chat(
        FakeHermes(b"", down={"/v1/chat"}), {"conversationId": cid, "message": "Still there?"}
    )

    stub = NoHermes()
    transport = httpx.ASGITransport(app=app_with(stub))
    async with api_client(transport) as c:
        res = await c.get(f"/api/conversations/{cid}/messages")
    assert res.status_code == 200 and stub.requests == []
    msgs = res.json()

    first_turn, aborted_id = meta(first)["turnId"], meta(aborted)["turnId"]
    offline_turn = meta(offline)["turnId"]
    doc_data = {c["id"]: c["data"] for c in first if c != "[DONE]" and c["type"] == "data-doc"}
    assert set(doc_data) == {search_doc, open_doc}

    def tool(call_id, name):
        return {
            "type": "dynamic-tool",
            "toolName": name,
            "toolCallId": call_id,
            "input": {},
            "state": "output-available",
            "output": {"status": "completed"},
        }

    def reasoning(chunks, rid):
        return {"type": "reasoning", "text": deltas(chunks, "reasoning", rid), "state": "done"}

    assert msgs == [
        {
            "id": f"{first_turn}:u",
            "role": "user",
            "parts": [{"type": "text", "text": "Find the URSSAF letter"}],
        },
        {
            "id": first[0]["messageId"],
            "role": "assistant",
            "metadata": {
                "conversationId": cid,
                "turnId": first_turn,
                "replyLanguage": "en",
                "reasoningMs": first[-2]["messageMetadata"]["reasoningMs"],
            },
            "parts": [
                reasoning(first, "r1"),
                tool("call_5d1ae2cb042d40e5ac21fd0b", "search_documents"),
                {"type": "data-doc", "id": search_doc, "data": doc_data[search_doc]},
                reasoning(first, "r2"),
                tool("call_ab02430a7e894e8dacdfa45f", "get_document"),
                {"type": "data-doc", "id": open_doc, "data": doc_data[open_doc]},
                reasoning(first, "r3"),
                {"type": "text", "text": deltas(first, "text", "t1"), "state": "done"},
            ],
        },
        {
            "id": f"{aborted_id}:u",
            "role": "user",
            "parts": [{"type": "text", "text": "And the EDF bill?"}],
        },
        {
            "id": aborted[0]["messageId"],
            "role": "assistant",
            "metadata": {
                "conversationId": cid,
                "turnId": aborted_id,
                "replyLanguage": "en",
                "reasoningMs": rows.turn_row(aborted_id).reasoning_ms,
            },
            "parts": [
                {"type": "reasoning", "text": "Let me look", "state": "done"},
                {
                    "type": "dynamic-tool",
                    "toolName": "get_document",
                    "toolCallId": "c9",
                    "input": {},
                    "state": "output-error",
                    "errorText": "stream_interrupted",
                },
                {"type": "text", "text": "Looking", "state": "done"},
            ],
        },
        {
            "id": f"{offline_turn}:u",
            "role": "user",
            "parts": [{"type": "text", "text": "Still there?"}],
        },
    ]
    assert rows.turn_row(aborted_id).status == "aborted"
    assert rows.turn_row(offline_turn).status == "failed"


async def test_reload_uses_current_state_skips_gone_subjects_and_dedupes_cards():
    doc, gone = rows.document("URSSAF appel", amount=10.0), rows.document("Gone")
    parts = [
        {"type": "data", "kind": "doc", "id": doc},
        {"type": "text", "text": "Here."},
        {"type": "data", "kind": "doc", "id": gone},
        {"type": "data", "kind": "doc", "id": doc},
    ]
    cid, _ = rows.turn(status="closed", parts=parts)
    with rows.connect() as conn:
        conn.execute("UPDATE documents SET title = 'Renamed' WHERE id = %s", (doc,))
        conn.execute(
            "UPDATE documents SET deleted_at = now(), location = 'trash' WHERE id = %s", (gone,)
        )
    transport = httpx.ASGITransport(app=app_with(NoHermes()))
    async with api_client(transport) as c:
        msgs = (await c.get(f"/api/conversations/{cid}/messages")).json()
    assistant = msgs[1]["parts"]
    assert [p["type"] for p in assistant] == ["data-doc", "text"]
    assert assistant[0]["data"]["title"] == "Renamed"


async def test_reload_of_an_unknown_conversation_is_404():
    transport = httpx.ASGITransport(app=app_with(NoHermes()))
    async with api_client(transport) as c:
        res = await c.get("/api/conversations/cnv_" + "0" * 26 + "/messages")
    assert res.status_code == 404 and res.json()["error"]["code"] == "not_found"

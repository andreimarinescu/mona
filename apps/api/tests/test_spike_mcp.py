import httpx
import pytest
from fastmcp import Client
from pydantic import SecretStr

from mona.app import create_app
from mona.settings import Settings
from mona.spike import mcp as spike_mcp
from tests.spike_rows import add_turn, card_rows

pytestmark = pytest.mark.usefixtures("clean_spike")


async def call(tool: str, **args):
    async with Client(spike_mcp.mcp) as client:
        return (await client.call_tool(tool, args)).structured_content


async def test_search_writes_one_doc_card_per_hit_and_returns_the_refs():
    _, turn = add_turn()
    res = await call("search_documents", query="AGIPI")
    assert res["document_ids"] == ["doc_agipi_per", "doc_agipi_av"]
    rows = card_rows()
    assert res["card_refs"] == [r.id for r in rows]
    assert [(r.tool, r.kind, r.subject, r.turn_id) for r in rows] == [
        ("search_documents", "doc", {"document_id": "doc_agipi_per"}, turn),
        ("search_documents", "doc", {"document_id": "doc_agipi_av"}, turn),
    ]


async def test_get_document_writes_one_card_and_unknown_ids_write_none():
    res = await call("get_document", document_id="doc_urssaf_q3")
    assert res["amount"] == 1284.0 and len(res["card_refs"]) == 1
    assert (await call("get_document", document_id="doc_nope"))["error"] == "not_found"
    assert len(card_rows()) == 1


async def test_start_interview_writes_one_interview_card_with_three_options():
    res = await call("start_interview", topic="AGIPI")
    (row,) = card_rows()
    assert res["card_refs"] == [row.id]
    assert (row.tool, row.kind, row.subject) == (
        "start_interview",
        "interview",
        {"interview_id": res["interview_id"]},
    )


@pytest.mark.parametrize(
    ("turns", "attributed"),
    [
        ([], False),
        ([("open", 120)], True),
        ([("open", 120), ("open", 120)], False),
        ([("open", -5)], False),
        ([("open", 120), ("closed", 120)], True),
    ],
)
async def test_attribution_needs_exactly_one_live_open_turn(turns, attributed):
    ids = [add_turn(status, expires)[1] for status, expires in turns]
    await call("get_document", document_id="doc_edf_sept")
    (row,) = card_rows()
    assert row.turn_id == (ids[0] if attributed else None)


async def test_telegram_cards_are_never_attributed():
    add_turn()
    await spike_mcp.record_cards("get_document", [("doc", {"document_id": "x"})], "telegram")
    assert card_rows()[0].turn_id is None


def _settings_with_key(monkeypatch):
    s = Settings(mona_service_key=SecretStr("k" * 32))  # type: ignore[call-arg]
    monkeypatch.setattr(spike_mcp, "get_settings", lambda: s)


INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "t", "version": "0"},
    },
}


@pytest.mark.parametrize(
    ("auth", "status"), [(None, 401), ("Bearer wrong", 401), ("Bearer " + "k" * 32, 200)]
)
async def test_mcp_endpoint_requires_the_service_key(monkeypatch, auth, status):
    _settings_with_key(monkeypatch)
    app = create_app()
    headers = {"accept": "application/json, text/event-stream"}
    if auth:
        headers["authorization"] = auth
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://api") as c:
            res = await c.post("/mcp", json=INIT, headers=headers)
    assert res.status_code == status

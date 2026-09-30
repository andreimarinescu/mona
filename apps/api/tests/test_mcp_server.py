import asyncio
import json
import logging
import socket
from datetime import date

import pytest

from mona.mcp import core, read
from mona.settings import get_settings
from tests import rows
from tests.conftest import SERVICE_KEY
from tests.mcp_http import call, list_tools, mcp_client, rpc, rpc_result
from tests.mcp_results import RESULT_MODELS

pytestmark = pytest.mark.usefixtures("clean")

READ_TOOLS = {
    "search_documents",
    "get_document",
    "sum_amounts",
    "list_review_queue",
    "list_deadlines",
    "get_brief",
}


# Auth and transport (C4 §1.1, §5.1)


@pytest.mark.parametrize(
    ("auth", "status"),
    [
        (None, 401),
        ("Bearer wrong", 401),
        (f"Bearer {SERVICE_KEY} ", 401),
        (SERVICE_KEY, 401),
        (f"Bearer {SERVICE_KEY}", 200),
    ],
)
async def test_the_service_key_gates_every_request(auth, status, caplog):
    doc = rows.document("URSSAF appel")
    caplog.set_level(logging.WARNING)
    res = await call("get_document", {"document_id": doc}, auth=auth)
    assert res.status == status
    if status == 401:
        assert json.loads(res.text) == {"error": "unauthorized"}
        assert rows.card_rows() == []
        assert "unauthorized" in caplog.text and SERVICE_KEY not in caplog.text
    else:
        assert not res.is_error and len(rows.card_rows()) == 1


async def test_a_short_configured_key_refuses_everything(monkeypatch):
    monkeypatch.setenv("MONA_SERVICE_KEY", "short")
    get_settings.cache_clear()
    try:
        res = await call("get_brief", auth="Bearer short")
    finally:
        monkeypatch.setenv("MONA_SERVICE_KEY", SERVICE_KEY)
        get_settings.cache_clear()
    assert res.status == 401


async def test_a_body_over_64_kib_is_413():
    async with mcp_client() as c:
        res = await rpc(c, "tools/call", {"name": "get_brief", "arguments": {"x": "y" * 70_000}})
    assert res.status_code == 413


async def test_only_tools_are_registered():
    tools = await list_tools()
    assert {t["name"] for t in tools} == READ_TOOLS
    async with mcp_client() as c:
        for method, key in (("resources/list", "resources"), ("prompts/list", "prompts")):
            assert rpc_result(await rpc(c, method))[key] == []


async def test_input_schemas_reject_unknown_keys_and_wrong_prefixes():
    for tool in await list_tools():
        assert tool["inputSchema"]["additionalProperties"] is False, tool["name"]
    for name, args in [
        ("search_documents", {"bogus": 1}),
        ("get_document", {"document_id": "ddl_01m3sg44rengv1yevkp7ca1xg5"}),
        ("sum_amounts", {"document_ids": ["rul_01m3sg44rengv1yevkp7ca1xg5"]}),
        ("list_review_queue", {"reason": "other"}),
        ("list_deadlines", {"within_days": 400}),
        ("get_brief", {"since": "yesterday"}),
    ]:
        res = await call(name, args)
        assert res.is_error and res.data["error"]["code"] == "invalid_argument", name


async def test_descriptions_are_the_contract_text():
    by_name = {t["name"]: t["description"] for t in await list_tools()}
    assert by_name["sum_amounts"].startswith("Add up document amounts, either for a list")
    assert by_name["get_brief"].endswith("amounts and due dates first, one short paragraph.")


# Channel (C4 §1.2) and attribution (C3 §5.2, §8.3)


@pytest.mark.parametrize(
    ("header", "channel"),
    [
        ("web", "web"),
        ("telegram", "telegram"),
        (None, "telegram"),
        ("Web", "telegram"),
        ("x", "telegram"),
    ],
)
async def test_channel_comes_from_the_header_and_defaults_to_telegram(header, channel):
    doc = rows.document("URSSAF appel")
    await call("get_document", {"document_id": doc}, channel=header)
    assert rows.card_rows()[0].channel == channel


@pytest.mark.parametrize(
    ("turns", "channel", "attributed"),
    [
        ([], "web", False),
        ([("open", 120)], "web", True),
        ([("open", 120), ("open", 120)], "web", False),
        ([("open", -5)], "web", False),
        ([("open", 120), ("closed", 120)], "web", True),
        ([("open", 120)], "telegram", False),
    ],
)
async def test_attribution_needs_exactly_one_live_open_web_turn(turns, channel, attributed):
    ids = [rows.turn(status=s, expires_in_s=e)[1] for s, e in turns]
    doc = rows.document("URSSAF appel")
    res = await call("get_document", {"document_id": doc}, channel=channel)
    (row,) = rows.card_rows()
    assert res.data["card_refs"] == [row.id]
    assert row.turn_id == (ids[0] if attributed else None)


# Errors and budget (C4 §2.4, §2.8)


async def test_not_found_uses_the_envelope():
    res = await call("get_document", {"document_id": "doc_01m3sg44rengv1yevkp7ca1xg5"})
    assert res.is_error
    assert res.data == {"error": {"code": "not_found", "message": "No document with that id."}}


async def test_unexpected_failures_are_internal_without_details(monkeypatch, caplog):
    async def broken(*_):
        raise RuntimeError("secret detail at /data/archive")

    monkeypatch.setattr(read, "scope_for", broken)
    res = await call("search_documents", {"query": "x"})
    assert res.is_error and res.data["error"]["code"] == "internal"
    assert "secret" not in res.text and "secret detail" in caplog.text


async def test_a_tool_over_its_time_budget_is_internal(monkeypatch):
    monkeypatch.setattr(core, "TOOL_BUDGET_S", 0.05)
    real = read.scope_for

    async def slow(*args):
        await asyncio.sleep(0.5)
        return await real(*args)

    monkeypatch.setattr(read, "scope_for", slow)
    res = await call("get_brief")
    assert res.is_error and res.data["error"]["code"] == "internal"


# Caps and pagination (C4 §2.3)


async def test_pages_follow_the_cursor_and_a_foreign_cursor_is_refused():
    ids = [rows.document(f"Facture {i:02}", doc_date=date(2025, 1, i + 1)) for i in range(12)]
    first = await call("search_documents", {"limit": 5})
    assert first.data["total"] == 12 and len(first.data["results"]) == 5
    second = await call("search_documents", {"limit": 5, "cursor": first.data["next_cursor"]})
    third = await call("search_documents", {"limit": 5, "cursor": second.data["next_cursor"]})
    assert third.data["next_cursor"] is None and len(third.data["results"]) == 2
    seen = [r["id"] for p in (first, second, third) for r in p.data["results"]]
    assert seen == list(reversed(ids))
    foreign = await call(
        "search_documents", {"limit": 5, "cursor": first.data["next_cursor"], "status": "filed"}
    )
    assert foreign.data["error"]["code"] == "invalid_argument"
    assert foreign.data["error"]["field"] == "cursor"
    junk = await call("search_documents", {"cursor": "not-a-cursor"})
    assert junk.data["error"]["code"] == "invalid_argument"


async def test_default_and_max_limits():
    for i in range(30):
        rows.document(f"Facture {i}")
    assert len((await call("search_documents")).data["results"]) == 10
    over = await call("search_documents", {"limit": 26})
    assert over.data["error"]["code"] == "invalid_argument"


async def test_long_results_drop_items_from_the_end_and_say_so():
    for i in range(25):
        rows.document(f"Facture {i:02} " + "très long intitulé " * 20, doc_date=date(2025, 1, 1))
    res = await call("search_documents", {"limit": 25})
    assert res.data["truncated"] is True and len(res.text) <= 4000
    shown = len(res.data["results"])
    assert 0 < shown < 25
    rest = await call("search_documents", {"limit": 25, "cursor": res.data["next_cursor"]})
    ids = {r["id"] for r in res.data["results"]}
    assert rest.data["results"] and not ids & {r["id"] for r in rest.data["results"]}


async def test_every_result_validates_and_fits_on_the_fixture_registry():
    for i in range(30):
        doc = rows.document(
            f"Appel de cotisation {i} " + "x" * 200,
            counterparty="opco",
            amount=100.0 + i,
            doc_date=date(2025, 3, 1),
            due_date=date(2026, 10, 20),
        )
        rows.deadline(f"Échéance {i} " + "y" * 200, date.today(), document_id=doc, amount=10.0)
        rows.document(f"Review {i}", status="review", reasons=("low", "entity"), entity=None)
    samples = {
        "search_documents": {"limit": 25},
        "get_document": {"document_id": doc},
        "sum_amounts": {"counterparty": "OPCO"},
        "list_review_queue": {"limit": 25},
        "list_deadlines": {"limit": 25},
        "get_brief": {},
    }
    for name, args in samples.items():
        res = await call(name, args)
        assert not res.is_error, (name, res.text)
        RESULT_MODELS[name].model_validate(res.data)
        assert len(res.text) <= 4000, name


# No egress (C4 §5.9)


async def test_no_tool_opens_a_socket(monkeypatch):
    doc = rows.document("URSSAF appel", counterparty="opco", amount=12.0)
    rows.deadline("URSSAF", date.today(), document_id=doc)

    def refuse(self, address):
        raise AssertionError(f"socket connect to {address}")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    for name, args in {
        "search_documents": {"query": "URSSAF"},
        "get_document": {"document_id": doc},
        "sum_amounts": {"document_ids": [doc]},
        "list_review_queue": {},
        "list_deadlines": {},
        "get_brief": {},
    }.items():
        res = await call(name, args)
        assert not res.is_error, (name, res.text)

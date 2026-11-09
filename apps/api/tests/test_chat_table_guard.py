"""A40: in a turn with a table card, the adapter drops markdown-table lines from the reply."""

import logging
from datetime import date

import httpx
import pytest

from mona.chat.guard import TableLineGuard
from mona.chat.stream import run_turn
from mona.chat.turns import open_turn
from mona.db import get_engine
from mona.i18n import t
from tests import rows
from tests.api_client import api_client
from tests.hermes_fake import FakeHermes, app_with, chunk, meta, post_chat, sse_body, tool_event
from tests.mcp_http import call

pytestmark = pytest.mark.usefixtures("clean")

TABLE = "| Title | Due |\n|---|---|\n| OPCO contribution | 2026-10-15 |\n"
BEFORE = "Here are your payables.\n\n"
AFTER = "\nThe IBAN column is blank; amounts | dates are in the card.\n  Ask for a file if needed."
CARD = {"type": "data-table", "id": "exp_1", "data": {}}


def run(guard: TableLineGuard, deltas: list[str], part: str = "t1") -> list[dict]:
    out = []
    for c in [
        {"type": "text-start", "id": part},
        *({"type": "text-delta", "id": part, "delta": d} for d in deltas),
        {"type": "text-end", "id": part},
    ]:
        out += guard.feed(c)
    return out


def kept(chunks: list) -> str:
    return "".join(c["delta"] for c in chunks if c != "[DONE]" and c["type"] == "text-delta")


def assert_paired(chunks: list) -> None:
    open_id = None
    for c in chunks:
        if c == "[DONE]" or not c["type"].startswith("text-"):
            continue
        if c["type"] == "text-start":
            assert open_id is None
            open_id = c["id"]
        else:
            assert c["id"] == open_id, c
            if c["type"] == "text-end":
                open_id = None
    assert open_id is None


def split_every(text: str, n: int) -> list[str]:
    return [text[i : i + n] for i in range(0, len(text), n)]


# The guard


@pytest.mark.parametrize("size", [1, 3, 7, 1000])
def test_a_table_split_across_deltas_is_dropped_and_the_prose_kept_byte_identical(size):
    guard = TableLineGuard()
    guard.feed(CARD)
    out = run(guard, split_every(BEFORE + TABLE + AFTER, size))
    assert kept(out) == BEFORE + AFTER
    assert guard.dropped == 3
    assert out[0]["type"] == "text-start" and out[-1] == {"type": "text-end", "id": "t1"}
    assert all(c["delta"] for c in out if c["type"] == "text-delta")


def test_indented_table_lines_go_and_a_bar_inside_prose_stays():
    guard = TableLineGuard()
    guard.feed(CARD)
    text = "  | a | b |\n\t|--|--|\nTotal | 3 rows\n   Note | kept\n|last"
    assert kept(run(guard, [text])) == "Total | 3 rows\n   Note | kept\n"
    assert guard.dropped == 3


def test_blanks_held_at_the_end_of_a_part_are_flushed_before_its_end():
    guard = TableLineGuard()
    guard.feed(CARD)
    out = run(guard, ["Done.\n", "  "])
    assert out[-2:] == [
        {"type": "text-delta", "id": "t1", "delta": "  "},
        {"type": "text-end", "id": "t1"},
    ]
    assert kept(out) == "Done.\n  "


def test_an_all_table_part_keeps_its_start_and_end_and_no_delta():
    guard = TableLineGuard()
    guard.feed(CARD)
    assert run(guard, [TABLE]) == [
        {"type": "text-start", "id": "t1"},
        {"type": "text-end", "id": "t1"},
    ]


def test_nothing_is_dropped_without_a_table_card_or_before_it():
    guard = TableLineGuard()
    guard.feed({"type": "data-doc", "id": "doc_1", "data": {}})
    assert kept(run(guard, [BEFORE + TABLE + AFTER])) == BEFORE + TABLE + AFTER
    before = [
        {"type": "text-start", "id": "t2"},
        {"type": "text-delta", "id": "t2", "delta": TABLE},
    ]
    assert [x for c in before for x in guard.feed(c)] == before
    guard.feed(CARD)
    assert guard.feed({"type": "text-delta", "id": "t2", "delta": TABLE}) == [
        {"type": "text-delta", "id": "t2", "delta": TABLE}
    ]
    assert guard.dropped == 0


# The adapter


def table_turn(*deltas: str, tool: str = "export_table") -> FakeHermes:
    doc = rows.document("OPCO contribution", amount=1284.6, due_date=date(2026, 10, 15))

    async def tools():
        if tool == "export_table":
            args = {"document_ids": [doc], "columns": ["title", "due_date"], "format": "table"}
        else:
            args = {"document_id": doc}
        res = await call(tool, args)
        assert not res.is_error, res.text

    body = sse_body(
        [
            *tool_event(tool, "c1", "running"),
            *tool_event(tool, "c1", "completed"),
            *(chunk({"content": d}) for d in deltas),
            chunk({}, "stop"),
            "data: [DONE]",
        ]
    )
    return FakeHermes(body, during_stream=tools)


async def test_the_stream_and_the_stored_parts_lose_the_table_lines(caplog):
    caplog.set_level(logging.INFO, logger="mona")
    _, chunks = await post_chat(table_turn(*split_every(BEFORE + TABLE + AFTER, 5)))
    types_ = [c if c == "[DONE]" else c["type"] for c in chunks]
    assert types_.index("data-table") < types_.index("text-start")
    assert kept(chunks) == BEFORE + AFTER
    assert_paired(chunks)
    turn_id = meta(chunks)["turnId"]
    parts = rows.turn_row(turn_id).parts
    assert [p["type"] for p in parts] == ["tool", "data", "text"]
    assert parts[-1]["text"] == BEFORE + AFTER
    assert f"turn {turn_id}: 3 table lines dropped" in caplog.text
    assert "OPCO" not in caplog.text


async def test_without_a_table_card_the_text_is_kept_and_nothing_is_logged(caplog):
    caplog.set_level(logging.INFO, logger="mona")
    _, chunks = await post_chat(table_turn(BEFORE + TABLE + AFTER, tool="get_document"))
    assert "data-doc" in [c["type"] for c in chunks if c != "[DONE]"]
    assert kept(chunks) == BEFORE + TABLE + AFTER
    assert rows.turn_row(meta(chunks)["turnId"]).parts[-1]["text"] == BEFORE + TABLE + AFTER
    assert "table lines dropped" not in caplog.text


@pytest.mark.parametrize(
    ("body", "lang"),
    [({}, "en"), ({"message": "Montrez-moi un tableau des factures à payer"}, "fr"),
     ({"replyLanguage": "ro"}, "ro")],
)  # fmt: skip
async def test_an_all_table_reply_gets_the_table_intro_not_the_fallback(body, lang):
    _, chunks = await post_chat(table_turn(*split_every(TABLE, 4)), **body)
    assert meta(chunks)["replyLanguage"] == lang
    assert kept(chunks) == t("chat.table.intro", lang)
    assert kept(chunks) != t("chat.fallback.too_complex", lang)
    assert_paired(chunks)
    texts = [p for p in rows.turn_row(meta(chunks)["turnId"]).parts if p["type"] == "text"]
    assert texts == [
        {"type": "text", "text": ""},
        {"type": "text", "text": t("chat.table.intro", lang)},
    ]


async def test_a_table_turn_with_no_text_at_all_gets_the_table_intro():
    _, chunks = await post_chat(table_turn())
    assert kept(chunks) == "Here's the table."


async def test_an_abort_after_the_table_card_stores_the_table_intro():
    turn = await open_turn(get_engine(), None, "Show me a table of payables", "en", None)
    frames = run_turn(get_engine(), table_turn(TABLE).client(), turn, "/", "Home")
    async for frame in frames:
        if '"type": "data-table"' in frame:
            break
    await frames.aclose()
    turn_row = rows.turn_row(turn.id)
    assert turn_row.status == "aborted"
    assert turn_row.parts[-1] == {"type": "text", "text": t("chat.table.intro", "en")}


async def test_the_transcript_reload_shows_the_filtered_text():
    _, chunks = await post_chat(table_turn(BEFORE, TABLE, AFTER))
    cid = meta(chunks)["conversationId"]
    transport = httpx.ASGITransport(app=app_with(FakeHermes()))
    async with api_client(transport) as c:
        res = await c.get(f"/api/conversations/{cid}/messages")
    assistant = res.json()[1]
    assert [p["type"] for p in assistant["parts"]] == ["dynamic-tool", "data-table", "text"]
    assert assistant["parts"][-1] == {"type": "text", "text": BEFORE + AFTER, "state": "done"}

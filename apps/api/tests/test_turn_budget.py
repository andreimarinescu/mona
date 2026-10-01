"""A28: the MCP server's turn budget."""

import pytest

from mona import clock
from mona.mcp.core import TELEGRAM_TURN_GAP_S, turn_budget
from mona.settings import get_settings
from tests import rows
from tests.mcp_http import call

pytestmark = pytest.mark.usefixtures("l4_db")
TODAY = clock.paris_today()
REFUSED = {
    "error": "budget_exhausted",
    "message": "Answer now with what you already have, and say plainly what you couldn't do.",
}


async def ran(tool: str = "get_brief", **kw) -> bool:
    res = await call(tool, **kw)
    assert not res.is_error, res.text
    return res.data != REFUSED


def effects() -> tuple:
    return (
        rows.one("SELECT count(*) FROM reminders")[0],
        rows.one("SELECT count(*) FROM file_ops")[0],
        rows.one("SELECT count(*) FROM card_events")[0],
    )


async def test_a_web_turn_runs_six_calls_then_refuses_a_write_without_running_it():
    rows.turn()
    doc = rows.document("SIE letter", entity="cabinet")
    for _ in range(6):
        assert await ran()
    before = effects()
    res = await call("schedule_reminder", {"document_id": doc, "remind_on": str(TODAY)})
    assert not res.is_error and res.data == REFUSED
    assert effects() == before == (0, 0, 0)
    assert not await ran()


async def test_a_new_turn_starts_a_new_count():
    cid, first = rows.turn()
    assert [await ran() for _ in range(7)] == [True] * 6 + [False]
    with rows.connect() as conn:
        conn.execute(
            "UPDATE chat_turns SET status = 'closed', closed_at = now() WHERE id = %s", (first,)
        )
    rows.turn(cid)
    assert [await ran() for _ in range(7)] == [True] * 6 + [False]


async def test_calls_with_no_attributed_web_turn_are_not_counted():
    rows.turn()
    rows.turn()
    assert [await ran() for _ in range(8)] == [True] * 8


async def test_the_budget_comes_from_the_setting(monkeypatch):
    monkeypatch.setenv("MONA_TURN_TOOL_BUDGET", "2")
    get_settings.cache_clear()
    try:
        rows.turn()
        assert [await ran() for _ in range(3)] == [True, True, False]
    finally:
        monkeypatch.delenv("MONA_TURN_TOOL_BUDGET")
        get_settings.cache_clear()


async def test_a_telegram_turn_is_a_run_of_calls_close_together(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(turn_budget, "_clock", lambda: now[0])
    for _ in range(6):
        now[0] += TELEGRAM_TURN_GAP_S - 1
        assert await ran(channel="telegram")
    assert not await ran(channel="telegram")
    now[0] += TELEGRAM_TURN_GAP_S + 1
    assert await ran(channel="telegram")

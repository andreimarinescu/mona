"""A58: the adapter cuts a runaway reasoning and ends the turn cleanly."""

import asyncio
import itertools
import json
import logging

import httpx
import pytest

from mona.chat.stream import run_turn
from mona.chat.translate import OpenReasoning
from mona.chat.turns import open_turn
from mona.chat.watchdog import ReasoningWatchdog
from mona.db import get_engine
from mona.i18n import t
from mona.settings import get_settings
from tests import rows
from tests.api_client import api_client
from tests.hermes_fake import FakeHermes, app_with, parse, tool_event, types

pytestmark = pytest.mark.usefixtures("clean")

ENVELOPE = {
    "id": "chatcmpl-5b0d2c7e9a1f4e3d8c6b5a4f3e2d1c0b",
    "object": "chat.completion.chunk",
    "created": 1790866800,
    "model": "mona",
}
STUCK = t("chat.fallback.stuck", "en")
LOOP_LINE = "Let me check which documents are due this month."
STATES = ("running", "completed")
REPLY = "Two documents are due this month: the supplier invoice and the insurance notice."


def recorded(delta: dict | None = None, finish: str | None = None) -> str:
    choice = {"index": 0, "delta": delta or {}, "finish_reason": finish}
    return "data: " + json.dumps({**ENVELOPE, "choices": [choice]})


def tokens(text: str) -> list[str]:
    """Model-sized deltas: a word and its trailing space or newline."""
    out, word = [], ""
    for ch in text:
        word += ch
        if ch in " \n":
            out.append(word)
            word = ""
    return out + ([word] if word else [])


def body(reasoning: str, text: str | None = REPLY, *, before: list[str] = ()) -> bytes:
    lines = [recorded({"role": "assistant"}), *before]
    lines += [recorded({"reasoning_content": d}) for d in tokens(reasoning)]
    if text is not None:
        lines += [recorded({"content": d}) for d in tokens(text)]
    lines += [recorded({}, "stop"), "data: [DONE]"]
    return ("\n\n".join(lines) + "\n\n").encode()


def ticking(step: float):
    counter = itertools.count()
    return lambda: 1000.0 + step * next(counter)


async def drive(fake: FakeHermes, clock=None, message: str = "What's due this month?"):
    engine = get_engine()
    turn = await open_turn(engine, None, message, "en", None)
    kwargs = {"clock": clock} if clock else {}
    frames = [f async for f in run_turn(engine, fake.client(), turn, "/", "Home", **kwargs)]
    return turn, parse("".join(frames))


def joined(chunks: list, kind: str) -> str:
    return "".join(c["delta"] for c in chunks if c != "[DONE]" and c["type"] == f"{kind}-delta")


async def reload(conversation_id: str) -> list:
    transport = httpx.ASGITransport(app=app_with(FakeHermes()))
    async with api_client(transport) as c:
        res = await c.get(f"/api/conversations/{conversation_id}/messages")
    assert res.status_code == 200
    return res.json()


def assert_tripped(turn, chunks: list) -> None:
    assert types(chunks)[-7:] == [
        "reasoning-end",
        "text-start",
        "text-delta",
        "text-end",
        "finish-step",
        "finish",
        "[DONE]",
    ]
    assert joined(chunks, "text") == STUCK
    assert chunks[-2]["finishReason"] == "other"
    row = rows.turn_row(turn.id)
    assert (row.status, row.error_code) == ("closed", "reasoning_cap")
    assert [p["type"] for p in row.parts] == ["reasoning", "text"]
    assert row.parts[0]["text"] == joined(chunks, "reasoning")
    assert row.parts[1] == {"type": "text", "text": STUCK}


def unique_steps(n: int) -> str:
    line = "Step {0}: compare the amount on line {0} with the ledger entry.\n"
    return "".join(line.format(i) for i in range(n))


# Unit: the three rules


def part(text: str, opened_at: float = 0.0, pid: str = "r1") -> OpenReasoning:
    return OpenReasoning(pid, text, opened_at)


def test_rule_a_trips_above_the_character_cap():
    dog = ReasoningWatchdog(100, 120, lambda: 0.0)
    assert dog.check(part("x" * 100)) is None
    trip = dog.check(part("x" * 101))
    assert (trip.reason, trip.chars) == ("chars", 101)


def test_rule_b_trips_on_the_fifth_normalised_repeat_of_a_long_line():
    dog = ReasoningWatchdog(12000, 120, lambda: 0.0)
    variants = [LOOP_LINE, "  " + LOOP_LINE.upper(), LOOP_LINE.replace(" ", "   "), LOOP_LINE]
    text = "".join(v + "\nHmm.\n" for v in variants)
    assert dog.check(part(text)) is None
    assert dog.check(part(text + LOOP_LINE)) is None
    trip = dog.check(part(text + LOOP_LINE + "\n"))
    assert trip.reason == "repeat"


def test_rule_b_ignores_lines_under_40_characters_and_counts_per_part():
    short = "x" * 39
    dog = ReasoningWatchdog(12000, 120, lambda: 0.0)
    assert dog.check(part((short + "\n") * 20)) is None
    text = (LOOP_LINE + "\n") * 4
    assert dog.check(part(text, pid="r1")) is None
    assert dog.check(part(text, pid="r2")) is None
    assert dog.check(part(text + LOOP_LINE + "\n", pid="r2")).reason == "repeat"


def test_rule_c_trips_once_the_part_is_open_the_time_cap():
    now = [0.0]
    dog = ReasoningWatchdog(12000, 120, lambda: now[0])
    now[0] = 119.9
    assert dog.check(part("thinking", opened_at=0.0)) is None
    now[0] = 120.0
    assert dog.check(part("thinking", opened_at=0.0)).reason == "time"
    assert dog.check(None) is None


# The adapter: one test per trip reason


async def test_a_reasoning_over_the_character_cap_is_cut(caplog):
    caplog.set_level(logging.INFO)
    turn, chunks = await drive(FakeHermes(body(unique_steps(400))))
    assert_tripped(turn, chunks)
    reasoning = joined(chunks, "reasoning")
    assert 12000 < len(reasoning) < 12100
    cut = [r.getMessage() for r in caplog.records if "reasoning cut" in r.getMessage()]
    assert cut == [f"turn {turn.id}: reasoning cut: chars, {len(reasoning)} chars"]
    assert "ledger" not in caplog.text
    assert REPLY not in joined(chunks, "text")

    messages = await reload(turn.conversation_id)
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[1]["id"] == chunks[0]["messageId"]
    assert messages[1]["parts"] == [
        {"type": "reasoning", "text": reasoning, "state": "done"},
        {"type": "text", "text": STUCK, "state": "done"},
    ]


async def test_a_reasoning_that_repeats_a_line_five_times_is_cut(caplog):
    caplog.set_level(logging.INFO)
    loop = "".join(f"{LOOP_LINE}\nThe archive has {n} candidates.\n" for n in range(12))
    turn, chunks = await drive(FakeHermes(body(loop)))
    assert_tripped(turn, chunks)
    assert joined(chunks, "reasoning").count(LOOP_LINE) == 5
    assert "reasoning cut: repeat," in caplog.text


async def test_a_reasoning_open_too_long_is_cut_and_the_hermes_request_closed(caplog):
    caplog.set_level(logging.INFO)
    sent, closed = [0], asyncio.Event()

    class Endless(FakeHermes):
        async def __call__(self, request):
            if request.url.path != "/v1/chat/completions":
                return await super().__call__(request)

            async def stream():
                try:
                    yield (recorded({"role": "assistant"}) + "\n\n").encode()
                    for i in range(200):
                        sent[0] += 1
                        yield (recorded({"reasoning_content": f"idea {i}, "}) + "\n\n").encode()
                        await asyncio.sleep(0)
                    yield (recorded({}, "stop") + "\n\ndata: [DONE]\n\n").encode()
                finally:
                    closed.set()

            return httpx.Response(200, content=stream())

    turn, chunks = await drive(Endless(), clock=ticking(7.0))
    assert_tripped(turn, chunks)
    assert "reasoning cut: time," in caplog.text
    await asyncio.wait_for(closed.wait(), 2)
    assert sent[0] < 50
    assert rows.turn_row(turn.id).reasoning_ms >= 120_000


async def test_the_caps_come_from_the_settings(monkeypatch):
    monkeypatch.setenv("MONA_CHAT_REASONING_MAX_CHARS", "500")
    get_settings.cache_clear()
    try:
        turn, chunks = await drive(FakeHermes(body(unique_steps(20))))
    finally:
        monkeypatch.delenv("MONA_CHAT_REASONING_MAX_CHARS")
        get_settings.cache_clear()
    assert_tripped(turn, chunks)
    assert 500 < len(joined(chunks, "reasoning")) < 600


async def test_a_trip_after_text_adds_no_fallback():
    before = [recorded({"content": d}) for d in tokens("Let me look that up.")]
    before += ["\n".join(tool_event("search_documents", "call_1", s)[:2]) for s in STATES]
    turn, chunks = await drive(FakeHermes(body(unique_steps(400), before=before)))
    assert types(chunks)[-4:] == ["reasoning-end", "finish-step", "finish", "[DONE]"]
    assert joined(chunks, "text") == "Let me look that up."
    row = rows.turn_row(turn.id)
    assert (row.status, row.error_code) == ("closed", "reasoning_cap")
    assert [p["type"] for p in row.parts] == ["text", "tool", "reasoning"]


# No trip


async def test_no_trip_while_text_flows():
    long_reply = (LOOP_LINE + "\n") * 10 + "x" * 13000
    turn, chunks = await drive(FakeHermes(body("Thinking.", long_reply)), clock=ticking(100.0))
    assert joined(chunks, "text") == long_reply
    assert chunks[-2]["finishReason"] == "stop"
    row = rows.turn_row(turn.id)
    assert (row.status, row.error_code) == ("closed", None)


async def test_no_trip_on_an_eight_item_enumeration_of_short_field_lines(caplog):
    caplog.set_level(logging.INFO)
    items = "".join(
        f"Item {i}: supplier invoice number {i} from the cleaning company\n"
        "- status: open\n"
        "currency: EUR\n"
        f"amount: {100 + i}.00\n"
        "- due within the next thirty days\n"
        for i in range(1, 9)
    )
    turn, chunks = await drive(FakeHermes(body("Listing the open items.\n" + items)))
    assert joined(chunks, "reasoning").count("- status: open") == 8
    assert joined(chunks, "text") == REPLY
    row = rows.turn_row(turn.id)
    assert (row.status, row.error_code, row.finish_reason) == ("closed", None, "stop")
    assert "reasoning cut" not in caplog.text


# Bookkeeping


async def test_an_aborted_turn_keeps_its_reasoning_time():
    engine = get_engine()
    turn = await open_turn(engine, None, "What's due this month?", "en", None)
    frames = run_turn(
        engine, FakeHermes(body("Thinking it through.")).client(), turn, "/", "Home",
        clock=ticking(1.0),
    )  # fmt: skip
    async for frame in frames:
        if '"type": "reasoning-delta"' in frame:
            break
    await frames.aclose()
    row = rows.turn_row(turn.id)
    assert row.status == "aborted"
    assert [p["type"] for p in row.parts] == ["reasoning"]
    assert row.reasoning_ms is not None and row.reasoning_ms > 0

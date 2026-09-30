import itertools
import json

from mona.chat.translate import SSEParser, Translator, translate_lines
from tests.fixtures import (
    S1_OVERLAY_GOLDEN,
    S1_OVERLAY_STREAM,
    S5_TWO_TOOLS_STREAM,
    fixture_lines,
    upstream_deltas,
)


def collapse(chunks):
    return [t for t, _ in itertools.groupby(c["type"] for c in chunks)]


def joined(chunks, kind):
    return "".join(c["delta"] for c in chunks if c["type"] == f"{kind}-delta")


def assert_well_formed(chunks):
    open_ids: dict[str, str] = {}
    for c in chunks:
        kind, _, phase = c["type"].rpartition("-")
        if kind not in ("text", "reasoning"):
            assert not open_ids, f"{c['type']} while {open_ids} open"
            continue
        if phase == "start":
            assert not open_ids, f"{c['type']} while {open_ids} open"
            open_ids[c["id"]] = kind
        else:
            assert open_ids.get(c["id"]) == kind, f"{c['type']} {c['id']} without start"
            if phase == "end":
                del open_ids[c["id"]]
    assert not open_ids


def test_s1_overlay_fixture_maps_reasoning_tool_and_text():
    chunks = translate_lines(fixture_lines(S1_OVERLAY_STREAM))
    assert collapse(chunks) == [
        "reasoning-start",
        "reasoning-delta",
        "reasoning-end",
        "tool-input-available",
        "tool-output-available",
        "reasoning-start",
        "reasoning-delta",
        "reasoning-end",
        "text-start",
        "text-delta",
        "text-end",
    ]
    assert joined(chunks, "reasoning") == upstream_deltas(S1_OVERLAY_STREAM, "reasoning_content")
    assert joined(chunks, "text") == upstream_deltas(S1_OVERLAY_STREAM, "content")
    assert [c["id"] for c in chunks if c["type"].endswith("-start")] == ["r1", "r2", "t1"]
    tool_in, tool_out = (c for c in chunks if c["type"].startswith("tool-"))
    assert tool_in == {
        "type": "tool-input-available",
        "toolCallId": "chatcmpl-tool-8e55056018ba2970",
        "toolName": "get_document",
        "input": {},
        "dynamic": True,
    }
    assert tool_out == {
        "type": "tool-output-available",
        "toolCallId": "chatcmpl-tool-8e55056018ba2970",
        "output": {"status": "completed"},
        "dynamic": True,
    }
    assert_well_formed(chunks)


def test_s1_fixture_finish_state_and_reasoning_time():
    ticks = itertools.count(0.0, 0.01)
    parser, tr = SSEParser(), Translator(clock=lambda: next(ticks))
    for line in fixture_lines(S1_OVERLAY_STREAM):
        ev = parser.feed(line)
        if ev:
            tr.feed(ev)
    assert tr.done
    assert tr.finish_reason == "stop" and tr.ui_finish_reason == "stop"
    assert tr.usage == {"prompt_tokens": 15830, "completion_tokens": 180, "total_tokens": 16010}
    assert tr.completed_tools == ["get_document"]
    assert tr.reasoning_ms > 0


def test_s5_two_tool_capture_emits_both_tool_pairs_in_order():
    chunks = translate_lines(fixture_lines(S5_TWO_TOOLS_STREAM))
    tools = [(c["type"], c.get("toolName")) for c in chunks if c["type"].startswith("tool-")]
    assert tools == [
        ("tool-input-available", "search_documents"),
        ("tool-output-available", None),
        ("tool-input-available", "get_document"),
        ("tool-output-available", None),
    ]
    assert joined(chunks, "text") == upstream_deltas(S5_TWO_TOOLS_STREAM, "content")
    assert_well_formed(chunks)


def _chunk(delta, finish=None):
    return "data: " + json.dumps(
        {"choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
    )


def test_completion_without_running_event_synthesises_the_input_part():
    lines = [
        _chunk({"content": "Looking"}),
        "event: hermes.tool.progress",
        'data: {"tool": "memory", "toolCallId": "c1", "status": "completed"}',
        "",
    ]
    assert collapse(translate_lines(lines)) == [
        "text-start",
        "text-delta",
        "text-end",
        "tool-input-available",
        "tool-output-available",
    ]
    assert translate_lines(lines)[3]["toolName"] == "memory"


def test_status_events_keepalives_and_role_chunks_are_dropped():
    lines = [
        _chunk({"role": "assistant"}),
        ": keepalive",
        "event: hermes.status",
        'data: {"status": "thinking"}',
        "",
        _chunk({"reasoning_content": "Hm"}),
        _chunk({}, finish="tool_calls"),
        "data: [DONE]",
    ]
    parser, tr, out = SSEParser(), Translator(), []
    for line in lines:
        ev = parser.feed(line)
        if ev:
            out += tr.feed(ev)
    assert collapse(out) == ["reasoning-start", "reasoning-delta", "reasoning-end"]
    assert tr.ui_finish_reason == "other"


def test_s1_overlay_fixture_matches_the_golden_chunks():
    golden = json.loads(S1_OVERLAY_GOLDEN.read_text())
    assert translate_lines(fixture_lines(S1_OVERLAY_STREAM)) == golden

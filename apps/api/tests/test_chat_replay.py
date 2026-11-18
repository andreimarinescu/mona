"""`mona chat-replay` (D23): scenarios from state.db, the streamed replay, a counts-only summary."""

import asyncio
import functools
import hashlib
import json
import sqlite3
import stat
import subprocess
from pathlib import Path

import httpx
import pytest
import yaml
from typer.testing import CliRunner

from mona import chat_replay as cr
from mona import hermes_schema as hs
from mona.chat import watchdog
from mona.cli import app
from mona.settings import Settings
from tests import rows

FIXTURES = Path(__file__).parent / "fixtures" / "replay"
WRAPPER = Path(__file__).resolve().parents[3] / "deploy" / "bin" / "mona"
BASE = "http://llm.test/v1"
BUDGET = "\n\nI have enough to answer now.\n"
PLANTED = {
    "prompt": "PLANTED-PROMPT-7f3a",
    "user": "PLANTED-USER-91bc",
    "history": "PLANTED-HISTORY-c2d4",
    "reasoning": "PLANTED-THOUGHT-5e6f",
    "content": "PLANTED-REPLY-0a1b",
    "args": "PLANTED-ARGUMENT-3c9d",
    "overlay": "PLANTED-OVERLAY-8d2e",
}
LONG_LINE = "the same line of reasoning that goes round again and again"


def settings(**kw) -> Settings:
    base = {
        "database_url": "postgresql+psycopg://x:y@h/d",
        "mona_env": "dev",
        "mona_llm_model": "qwen-test",
        "mona_llm_base_url": BASE,
    }
    return Settings(**{**base, **kw})


def sse(*deltas: dict, usage: dict | None = None) -> list[bytes]:
    lines = [f"data: {json.dumps({'choices': [{'delta': d}]})}\n\n".encode() for d in deltas]
    if usage:
        lines.append(f"data: {json.dumps({'choices': [], 'usage': usage})}\n\n".encode())
    return [*lines, b"data: [DONE]\n\n"]


def transport(chunks, seen: list | None = None, delay: float = 0.0, status: int = 200):
    """A fake streaming endpoint; `chunks` is a list of bytes or a callable yielding them."""

    async def body():
        source = chunks() if callable(chunks) else iter(chunks)
        for chunk in source:
            if delay:
                await asyncio.sleep(delay)
            yield chunk

    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        if request.url.path.endswith("/props"):
            return httpx.Response(200, json={"build_info": "b-test"})
        if status != 200:
            return httpx.Response(status, json={"error": {"message": PLANTED["content"]}})
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, stream=_Stream(body())
        )

    return httpx.MockTransport(handler)


class _Stream(httpx.AsyncByteStream):
    def __init__(self, source) -> None:
        self.source = source

    async def __aiter__(self):
        async for chunk in self.source:
            yield chunk


def scenario(**kw) -> dict:
    return {
        "v": 1,
        "system": {"prompt": f"Stored prompt. {PLANTED['prompt']}"},
        "overlay": {"language": "en"},
        "history": [{"role": "user", "content": PLANTED["history"]}],
        "user": PLANTED["user"],
        "tools": [],
        **kw,
    }


def replay(chunks, *, scenarios=None, seen=None, delay=0.0, **kw) -> dict:
    opts = {"runs": 1, "extra": {}, "extra_source": "none", "max_seconds": 5.0}
    return asyncio.run(
        cr.run_replay(
            kw.pop("cfg", settings()),
            scenarios or {"s": scenario()},
            transport=transport(chunks, seen, delay),
            **{**opts, **kw},
        )
    )


def only(summary: dict) -> dict:
    return summary["runs"]["s"][0]


# --- a synthetic Hermes state.db ---


def state_db(path: Path, session: str = "cnv_t") -> Path:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE system_prompts (hash TEXT PRIMARY KEY, prompt TEXT NOT NULL);
        CREATE TABLE sessions (id TEXT PRIMARY KEY, system_prompt TEXT, system_prompt_hash TEXT);
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, role TEXT NOT NULL,
            content TEXT, tool_call_id TEXT, tool_calls TEXT, active INTEGER NOT NULL DEFAULT 1);
        """
    )
    conn.execute("INSERT INTO system_prompts VALUES ('h1', 'STORED')")
    conn.execute("INSERT INTO sessions VALUES (?, NULL, 'h1')", (session,))
    call = [
        {
            "id": "c1",
            "type": "function",
            "function": {"name": "mcp__mona__list_deadlines", "arguments": "{}"},
        }
    ]
    msgs = [
        ("user", "What is due?", None, None, 1),
        ("assistant", "", None, json.dumps(call), 1),
        ("tool", '{"total": 0}', "c1", None, 1),
        ("assistant", "Nothing is due.", None, None, 1),
        ("user", "Marchez-le comme payé", None, None, 1),
        ("user", "dropped by compression", None, None, 0),
    ]
    conn.executemany(
        "INSERT INTO messages (session_id, role, content, tool_call_id, tool_calls, active)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        [(session, *m) for m in msgs],
    )
    conn.commit()
    conn.close()
    return path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def test_build_makes_one_scenario_per_turn_from_the_stored_session(tmp_path, clean):
    cnv = rows.conversation()
    db = state_db(tmp_path / "state.db", cnv)
    rows.turn(cnv, user_text="What is due?", reply_language="en", status="closed")
    rows.turn(cnv, user_text="Marchez-le comme payé", reply_language="ro", status="closed")
    before = digest(db)
    tools = await cr.mona_tools()

    made = cr.build_scenarios(db, cnv, [2, 1], tools)

    assert list(made) == [f"{cnv}-t2", f"{cnv}-t1"]
    first, second = made[f"{cnv}-t1"], made[f"{cnv}-t2"]
    assert first["system"] == {"prompt": "STORED"} and first["history"] == []
    assert first["overlay"]["language"] == "en" and "Reply in English" in first["overlay"]["text"]
    assert (
        second["overlay"]["language"] == "ro" and "Reply in Romanian" in second["overlay"]["text"]
    )
    assert second["user"] == "Marchez-le comme payé"
    assert [m["role"] for m in second["history"]] == ["user", "assistant", "tool", "assistant"]
    assert second["history"][1]["tool_calls"][0]["function"]["name"] == "mcp__mona__list_deadlines"
    assert second["history"][2] == {"role": "tool", "tool_call_id": "c1", "content": '{"total": 0}'}
    names = {t["function"]["name"] for t in second["tools"]}
    assert "mcp__mona__list_deadlines" in names and "mcp__mona__ingest_attachment" not in names
    assert all(n.startswith("mcp__mona__") for n in names)
    assert digest(db) == before


def test_build_falls_back_to_the_detected_language_without_a_recorded_turn(tmp_path):
    db = state_db(tmp_path / "state.db")
    made = cr.build_scenarios(db, "cnv_t", [2], [], languages=lambda _: [])
    assert made["cnv_t-t2"]["overlay"]["language"] == "fr"


def test_a_repeated_user_text_takes_the_language_recorded_for_that_occurrence(tmp_path):
    db = state_db(tmp_path / "state.db")
    conn = sqlite3.connect(db)
    conn.execute("UPDATE messages SET content = 'What is due?' WHERE content LIKE 'Marchez%'")
    conn.commit()
    conn.close()
    recorded = [("What is due?", "en"), ("What is due?", "ro")]
    made = cr.build_scenarios(db, "cnv_t", [1, 2], [], languages=lambda _: recorded)
    assert made["cnv_t-t1"]["overlay"]["language"] == "en"
    assert made["cnv_t-t2"]["overlay"]["language"] == "ro"


def test_the_ops_container_layout_has_no_repo_root_and_still_guards_and_finds_soul(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(cr, "__file__", "/app/src/mona/chat_replay.py")
    assert cr.repo_root() is None
    with pytest.raises(cr.ReplayError, match="inside /app"):
        cr.private_out(Path("/app/out"))
    assert cr.private_out(tmp_path / "ok") == (tmp_path / "ok").resolve()
    (tmp_path / "seed").mkdir()
    (tmp_path / "seed" / "SOUL.md").write_text("# Mona\n")
    monkeypatch.setenv("MONA_HERMES_SEED", str(tmp_path / "seed"))
    assert cr.soul_path() == tmp_path / "seed" / "SOUL.md"


def test_build_refuses_a_missing_turn_session_or_prompt(tmp_path):
    db = state_db(tmp_path / "state.db")
    with pytest.raises(cr.ReplayError, match="2 user messages"):
        cr.build_scenarios(db, "cnv_t", [3], [], languages=lambda _: [])
    with pytest.raises(cr.ReplayError, match="not in"):
        cr.build_scenarios(db, "cnv_other", [1], [], languages=lambda _: [])
    with pytest.raises(cr.ReplayError, match="no such file"):
        cr.build_scenarios(tmp_path / "none.db", "cnv_t", [1], [], languages=lambda _: [])


def test_build_command_writes_private_files_and_refuses_the_repo(tmp_path, monkeypatch):
    db = state_db(tmp_path / "state.db")
    monkeypatch.setattr(cr, "turn_languages", lambda _: [])
    monkeypatch.setattr(
        cr, "build_scenarios", functools.partial(cr.build_scenarios, languages=lambda _: [])
    )
    out = tmp_path / "out"
    res = CliRunner().invoke(
        app,
        [
            "chat-replay",
            "build",
            "--session",
            "cnv_t",
            "--turn",
            "1",
            "--turn",
            "2",
            "--hermes-db",
            str(db),
            "--out",
            str(out),
        ],
    )
    assert res.exit_code == 0, res.output
    files = sorted(out.glob("*.json"))
    assert [f.name for f in files] == ["cnv_t-t1.json", "cnv_t-t2.json"]
    assert all(stat.S_IMODE(f.stat().st_mode) == 0o600 for f in files)
    assert json.loads(files[1].read_text())["user"] == "Marchez-le comme payé"

    inside = cr.repo_root() / "tmp-replay"
    res = CliRunner().invoke(
        app,
        [
            "chat-replay",
            "build",
            "--session",
            "cnv_t",
            "--turn",
            "1",
            "--hermes-db",
            str(db),
            "--out",
            str(inside),
        ],
    )
    assert res.exit_code == 2 and "inside" in res.output
    assert not inside.exists()


def test_out_is_refused_inside_the_repo_and_the_ops_containers_code_and_seed(tmp_path):
    assert {str(p) for p in cr.PRIVATE_ROOTS} == {"/app", "/hermes-seed", "/seed"}
    for bad in (cr.repo_root() / "x", Path("/app/x"), Path("/hermes-seed"), Path("/seed/a/b")):
        with pytest.raises(cr.ReplayError, match="inside"):
            cr.private_out(bad)
    assert cr.private_out(tmp_path / "ok") == (tmp_path / "ok").resolve()


# --- the replayed request ---


def test_the_request_has_one_system_message_the_history_the_user_and_the_extra_body():
    seen: list[httpx.Request] = []
    stream = sse({"content": "Done."})
    replay(stream, seen=seen, extra={"presence_penalty": 1.5}, extra_source="inline")
    (req,) = [r for r in seen if r.url.path.endswith("/chat/completions")]
    body = json.loads(req.content)
    assert str(req.url) == f"{BASE}/chat/completions"
    assert body["model"] == "qwen-test" and body["stream"] is True
    assert body["presence_penalty"] == 1.5 and body["reasoning_effort"] == "medium"
    assert body["stream_options"] == {"include_usage": True}
    roles = [m["role"] for m in body["messages"]]
    assert roles == ["system", "user", "user"]
    system = body["messages"][0]["content"]
    assert system.startswith("Stored prompt.") and "Reply in English" in system
    assert "\n\nMona app context" in system
    assert body["messages"][-1] == {"role": "user", "content": PLANTED["user"]}
    assert "tools" not in body
    assert "authorization" not in req.headers


def test_a_soul_scenario_takes_the_current_soul_and_the_registry_tools():
    seen: list[httpx.Request] = []
    soul = json.loads((FIXTURES / "due-this-month.json").read_text())
    replay(sse({"content": "x"}), scenarios={"s": soul}, seen=seen)
    body = json.loads([r for r in seen if r.url.path.endswith("completions")][0].content)
    soul_text = (cr.repo_root() / "deploy" / "hermes" / "SOUL.md").read_text()
    assert body["messages"][0]["content"].startswith(soul_text.strip())
    names = {t["function"]["name"] for t in body["tools"]}
    assert "mcp__mona__list_deadlines" in names and "mcp__mona__ingest_attachment" not in names


def test_system_replaces_the_stored_prompt_and_the_cut_applies_to_it(tmp_path):
    cut_file = tmp_path / "cut.py"
    cut_file.write_text(
        "def cut_system_prompt(text):\n"
        "    return text.replace('DROP-ME', ''), ['drop-me'] if 'DROP-ME' in text else []\n"
    )
    seen: list[httpx.Request] = []
    out = replay(
        sse({"content": "x"}),
        seen=seen,
        system="Replacement DROP-ME prompt",
        cut=cr.load_cut(cut_file),
    )
    body = json.loads([r for r in seen if r.url.path.endswith("completions")][0].content)
    assert body["messages"][0]["content"].startswith("Replacement  prompt")
    assert PLANTED["prompt"] not in body["messages"][0]["content"]
    assert out["settings"]["cut"] is True and out["settings"]["cut_removed"] == {"drop-me": 1}
    assert out["settings"]["system_override"] is True
    assert not (tmp_path / "__pycache__").exists()


def test_load_cut_refuses_a_file_without_the_function(tmp_path):
    bad = tmp_path / "cut.py"
    bad.write_text("x = 1\n")
    with pytest.raises(cr.ReplayError, match="no cut_system_prompt"):
        cr.load_cut(bad)
    with pytest.raises(cr.ReplayError, match="no such file"):
        cr.load_cut(tmp_path / "missing.py")


def test_openrouter_gets_its_key_and_a_local_endpoint_does_not():
    seen: list[httpx.Request] = []
    cfg = settings(mona_llm_base_url=None, openrouter_api_key="sk-test-key")
    replay(sse({"content": "x"}), seen=seen, cfg=cfg)
    (req,) = seen
    assert req.url.host == "openrouter.ai" and req.headers["authorization"] == "Bearer sk-test-key"
    local: list[httpx.Request] = []
    replay(sse({"content": "x"}), seen=local, cfg=settings(openrouter_api_key="sk-test-key"))
    assert local and all("authorization" not in r.headers for r in local)


# --- the tools as Hermes registers them ---


def test_a_tool_schema_is_normalised_as_hermes_registers_it():
    schema = {
        "type": "object",
        "properties": {
            "entity": {"anyOf": [{"type": "string", "maxLength": 9}, {"type": "null"}],
                       "default": None, "description": "Entity key."},
            "kind": {"anyOf": [{"const": "a"}, {"const": "b"}, {"type": "null"}]},
            "where": {"$ref": "#/definitions/Where"},
            "opts": {"type": "object"},
        },
        "required": ["kind", "ghost"],
        "definitions": {"Where": {"properties": {"path": {"type": "string"}}, "required": ["x"]}},
    }  # fmt: skip
    tool = hs.openai_tool("mona", "find", "Find things.", schema)
    assert tool["function"]["name"] == "mcp__mona__find"
    assert json.dumps(tool["function"]["parameters"]) == json.dumps({
        "type": "object",
        "properties": {
            "entity": {"type": "string", "maxLength": 9, "nullable": True,
                       "description": "Entity key.", "default": None},
            "kind": {"type": "string", "enum": ["a", "b"], "nullable": True},
            "where": {"$ref": "#/$defs/Where"},
            "opts": {"type": "object", "properties": {}, "required": []},
        },
        "required": ["kind"],
        "$defs": {"Where": {"properties": {"path": {"type": "string"}}, "required": [],
                            "type": "object"}},
    })  # fmt: skip
    empty = hs.openai_tool("mona", "ping", None, None)["function"]
    assert empty["parameters"] == {"type": "object", "properties": {}}
    assert empty["description"] == "MCP tool ping from mona"
    assert hs.tool_name("mona", "a-b.c") == "mcp__mona__a_b_c"
    long = hs.tool_name("mona", "x" * 80)
    assert len(long) == 64 and long == hs.tool_name("mona", "x" * 80)


async def test_the_registry_tools_are_sorted_normalised_and_without_ingest_attachment():
    tools = await cr.mona_tools()
    names = [t["function"]["name"] for t in tools]
    assert names == sorted(names) and "mcp__mona__ingest_attachment" not in names
    text = json.dumps(tools)
    assert '"anyOf"' not in text and '"nullable": true' in text
    assert all(isinstance(t["function"]["parameters"]["required"], list) for t in tools)


# --- the stream, per run ---


def test_a_reasoning_only_stream_is_cut_at_max_seconds_and_counts_as_a_runaway():
    def endless():
        n = 0
        while True:
            n += 1
            yield sse({"reasoning_content": f"thinking step {n}\n"})[0]

    out = replay(endless, delay=0.02, max_seconds=0.3)
    rec = only(out)
    assert rec["runaway"] and rec["runaway_reason"] == "no_act" and not rec["acted"]
    assert rec["reasoning_chars"] > 100 and rec["first_act_s"] is None
    assert 0.25 <= rec["total_s"] < 2 and rec["reasoning_s"] > 0.1
    assert out["scenarios"]["s"]["runaway"] == 1


def test_a_run_that_acted_and_then_ran_past_max_seconds_is_not_a_runaway():
    def acted_then_endless():
        yield sse({"content": "Here is the answer."})[0]
        n = 0
        while True:
            n += 1
            yield sse({"reasoning_content": f"more {n}\n"})[0]

    rec = only(replay(acted_then_endless, delay=0.02, max_seconds=0.3))
    assert rec["acted"] and not rec["runaway"] and rec["runaway_reason"] is None
    assert rec["total_s"] >= 0.25


def test_an_act_resets_the_repeat_count():
    four = [sse({"reasoning_content": LONG_LINE + "\n"})[0]] * 4
    chunks = [*four, sse({"content": "Checking."})[0], *four, *sse({"content": "Done."})]
    rec = only(replay(chunks))
    assert rec["acted"] and not rec["runaway"]


def test_the_repeat_rule_is_the_adapters():
    assert cr.line_key is watchdog.line_key
    assert (cr.MIN_LINE, cr.REPEATS) == (watchdog.MIN_LINE, watchdog.REPEATS) == (40, 5)
    variants = [LONG_LINE, LONG_LINE.upper(), "\t" + LONG_LINE.title(),
                LONG_LINE.replace(" ", "  "), f" {LONG_LINE} "]  # fmt: skip
    watch = cr.RepeatWatch()
    assert [watch.feed(v + "\n") for v in variants] == [False, False, False, False, True]


def test_one_long_line_repeated_five_times_is_a_runaway_and_stops_the_read():
    sent = []

    def looping():
        for _ in range(40):
            sent.append(1)
            yield sse({"reasoning_content": LONG_LINE + "\n"})[0]

    rec = only(replay(looping, delay=0.001))
    assert rec["runaway"] and rec["runaway_reason"] == "repeat"
    assert len(sent) < 40


def test_short_or_fewer_repeats_are_not_a_runaway():
    short = [sse({"reasoning_content": "status: open\n"})[0]] * 8
    few = [sse({"reasoning_content": LONG_LINE + "\n"})[0]] * 4
    for chunks in (short, few):
        rec = only(replay([*chunks, *sse({"content": "ok"})]))
        assert not rec["runaway"] and rec["acted"]


def test_the_repeat_watch_normalises_and_counts_the_unterminated_last_line():
    watch = cr.RepeatWatch()
    spaced = "  " + LONG_LINE.upper().replace(" ", "   ")
    assert not any(watch.feed(spaced + "\n") for _ in range(4))
    assert watch.feed(spaced[:20]) is False
    assert watch.feed(spaced[20:]) is False
    assert watch.finish() is True


def test_a_tool_call_is_an_act_and_its_name_is_counted():
    chunks = sse(
        {"reasoning_content": "hmm"},
        {
            "tool_calls": [
                {
                    "index": 0,
                    "id": "c",
                    "function": {"name": "mcp__mona__list_deadlines", "arguments": ""},
                }
            ]
        },
        {"tool_calls": [{"index": 0, "function": {"arguments": '{"a": 1}'}}]},
    )
    out = replay(chunks)
    rec = only(out)
    assert rec["acted"] and not rec["runaway"] and rec["tools"] == ["mcp__mona__list_deadlines"]
    assert rec["content_chars"] == 0 and rec["first_act_s"] is not None
    assert out["scenarios"]["s"]["tools"] == {"mcp__mona__list_deadlines": 1}


def test_content_is_an_act_blank_content_is_not_and_the_reply_language_is_detected():
    blank = only(replay(sse({"content": "  \n"})))
    assert not blank["acted"] and not blank["runaway"]
    words = "Your next payment is due on the first of the month and what is due for this month"
    rec = only(
        replay(
            sse(
                {"reasoning": "think"},
                {"content": words},
                usage={"completion_tokens_details": {"reasoning_tokens": 12}},
            )
        )
    )
    assert rec["acted"] and rec["language"] == "en" and rec["content_chars"] == len(words)
    assert rec["reasoning_tokens"] == 12 and rec["reasoning_chars"] == 5


def test_a_reported_zero_reasoning_tokens_is_kept_and_the_table_shows_n():
    usage = {"completion_tokens_details": {"reasoning_tokens": 0}}
    out = replay(sse({"content": "Answer."}, usage=usage), runs=2)
    assert only(out)["reasoning_tokens"] == 0
    s = out["scenarios"]["s"]
    assert s["reasoning_tokens"] == {"n": 2, "p50": 0, "p95": 0, "max": 0}
    md = cr.markdown(out)
    assert "| 0 / 0 / 0 (n=2) |" in md and f"| {_triple_of(s['act_s'])} (n=2) |" in md
    assert "Reasoning effort: `medium` (default)" in md


def _triple_of(s: dict) -> str:
    return f"{s['p50']} / {s['p95']} / {s['max']}"


def test_reasoning_ending_with_the_budget_message_is_flagged():
    extra = {"reasoning_budget_message": BUDGET}
    ended = sse(
        {"reasoning_content": "a long thought"},
        {"reasoning_content": BUDGET},
        {"content": "Answer."},
    )
    plain = sse({"reasoning_content": "a long thought"}, {"content": "Answer."})
    assert only(replay(ended, extra=extra))["budget_hit"] is True
    assert only(replay(plain, extra=extra))["budget_hit"] is False
    resumed = sse(
        {"reasoning_content": BUDGET}, {"reasoning_content": "and more"}, {"content": "A."}
    )
    assert only(replay(resumed, extra=extra))["budget_hit"] is False
    assert only(replay(ended))["budget_hit"] is False


def test_an_http_error_is_recorded_as_a_code_only():
    rec = only(
        asyncio.run(
            cr.run_replay(
                settings(),
                {"s": scenario()},
                runs=1,
                extra={},
                extra_source="none",
                transport=transport([], status=429),
            )
        )
    )
    assert rec["error"] == "http_429" and not rec["acted"] and not rec["runaway"]
    assert PLANTED["content"] not in json.dumps(rec)


def test_the_summary_has_percentiles_histograms_runs_and_the_server_build():
    out = replay(
        sse({"reasoning_content": "abc"}, {"content": "Bonjour, voici ce qui est dû"}), runs=3
    )
    s = out["scenarios"]["s"]
    assert s["n"] == 3 and s["acted"] == 3 and s["runaway"] == 0
    assert s["reasoning_chars"] == {"n": 3, "p50": 3, "p95": 3, "max": 3}
    assert s["languages"] == {"fr": 3} and s["tools"] == {}
    assert out["llama_server"] == {"build_info": "b-test"} and out["model"] == "qwen-test"
    assert out["endpoint"] == "local"
    md = cr.markdown(out)
    assert "| s | 3 | 3 | 0 |" in md and "b-test" in md


def test_a_file_that_is_not_a_scenario_is_refused_before_any_run(tmp_path, monkeypatch):
    scen = write_scenarios(tmp_path / "scen")
    (scen / "summary.json").write_text(json.dumps({"v": 1, "scenarios": {}}))
    with pytest.raises(cr.ReplayError, match=r"summary\.json: not a scenario"):
        cr.load_scenarios(scen)
    seen: list[httpx.Request] = []
    res = run_cli(tmp_path, monkeypatch, "--scenarios", str(scen), "--no-extra", seen=seen)
    assert res.exit_code == 2 and "summary.json" in res.output and seen == []
    bad = {
        "user": scenario(user=""),
        "overlay": scenario(overlay={}),
        "system": scenario(system={"soul": False}),
        "history": scenario(history="x"),
    }
    for key, spec in bad.items():
        (scen / "summary.json").write_text(json.dumps(spec))
        with pytest.raises(cr.ReplayError, match=rf"not a scenario \(.*{key}"):
            cr.load_scenarios(scen)
    (scen / "summary.json").write_text("{")
    with pytest.raises(cr.ReplayError, match="not readable JSON"):
        cr.load_scenarios(scen)


# --- the extra body ---


def config(tmp_path: Path, extra: dict | None, base: str = BASE) -> Path:
    path = tmp_path / "config.yaml"
    entry = {"name": "mona", "base_url": base, **({"extra_body": extra} if extra else {})}
    path.write_text(yaml.safe_dump({"model": {"base_url": BASE}, "custom_providers": [entry]}))
    return path


def test_extra_from_takes_the_matching_providers_extra_body(tmp_path):
    extra = {"presence_penalty": 1.5, "reasoning_budget_tokens": 1024}
    path = config(tmp_path, extra)
    assert cr.merge_extra(path, None, none=False) == (extra, "config")
    assert cr.merge_extra(path, {"top_k": 20}, none=False)[0] == {**extra, "top_k": 20}


def test_a_config_that_yields_no_extra_body_stops_the_run_and_names_why(tmp_path, monkeypatch):
    other = config(tmp_path, {"presence_penalty": 1.5}, "http://other/v1")
    with pytest.raises(cr.ReplayError, match=r"no provider entry .* matches model\.base_url"):
        cr.merge_extra(other, None, none=False)
    bare = config(tmp_path, None)
    with pytest.raises(cr.ReplayError, match="matches model.base_url"):
        cr.merge_extra(bare, None, none=False)
    monkeypatch.delenv("MONA_TEST_BASE", raising=False)
    unset = tmp_path / "unset.yaml"
    entry = {"base_url": "${MONA_TEST_BASE}", "extra_body": {"top_k": 20}}
    unset.write_text(
        yaml.safe_dump({"model": {"base_url": "${MONA_TEST_BASE}"}, "custom_providers": [entry]})
    )
    with pytest.raises(cr.ReplayError, match=r"\$\{MONA_TEST_BASE\} in a base_url is not set"):
        cr.merge_extra(unset, None, none=False)
    monkeypatch.setenv("MONA_TEST_BASE", BASE)
    assert cr.merge_extra(unset, None, none=False)[0] == {"top_k": 20}
    assert cr.merge_extra(other, {"top_k": 20}, none=False) == ({"top_k": 20}, "config+inline")
    assert cr.merge_extra(other, None, none=True) == ({}, "none")


def test_the_run_command_refuses_a_config_without_an_extra_body(tmp_path, monkeypatch):
    scen = write_scenarios(tmp_path / "scen")
    seen: list[httpx.Request] = []
    other = config(tmp_path, {"presence_penalty": 1.5}, "http://other/v1")
    res = run_cli(tmp_path, monkeypatch, "--scenarios", str(scen), "--extra-from", str(other),
                  seen=seen)  # fmt: skip
    assert res.exit_code != 0 and "matches model.base_url" in res.output and seen == []


def test_extra_overrides_keys_and_no_extra_sends_nothing(tmp_path):
    path = config(tmp_path, {"presence_penalty": 1.5, "reasoning_budget_tokens": 1024})
    body, source = cr.merge_extra(path, {"reasoning_budget_tokens": 256, "top_k": 20}, none=False)
    assert body == {"presence_penalty": 1.5, "reasoning_budget_tokens": 256, "top_k": 20}
    assert source == "config+inline"
    assert cr.merge_extra(None, {"top_k": 20}, none=False) == ({"top_k": 20}, "inline")
    assert cr.merge_extra(path, None, none=True) == ({}, "none")
    with pytest.raises(cr.ReplayError, match="--extra-from"):
        cr.merge_extra(tmp_path / "missing.yaml", None, none=False)


def run_cli(tmp_path, monkeypatch, *args, chunks=None, seen=None):
    monkeypatch.setenv("MONA_LLM_BASE_URL", BASE)
    monkeypatch.setattr(
        cr,
        "run_replay",
        functools.partial(
            cr.run_replay,
            transport=transport(chunks or sse({"content": "ok"}), seen),
        ),
    )
    from mona.settings import get_settings

    get_settings.cache_clear()
    try:
        return CliRunner().invoke(app, ["chat-replay", "run", *args])
    finally:
        get_settings.cache_clear()


def write_scenarios(directory: Path, **kw) -> Path:
    directory.mkdir()
    (directory / "s.json").write_text(json.dumps(scenario(**kw)))
    return directory


def test_run_command_sends_the_config_extra_over_which_extra_wins_and_no_extra_sends_none(
    tmp_path, monkeypatch
):
    scen = write_scenarios(tmp_path / "scen")
    path = config(tmp_path, {"presence_penalty": 1.5, "reasoning_budget_tokens": 1024})

    def body_of(*flags):
        seen: list[httpx.Request] = []
        res = run_cli(
            tmp_path, monkeypatch, "--scenarios", str(scen), "--runs", "1", *flags, seen=seen
        )
        assert res.exit_code == 0, res.output
        posts = [r for r in seen if r.url.path.endswith("completions")]
        return json.loads(posts[0].content)

    merged = body_of("--extra-from", str(path), "--extra", '{"reasoning_budget_tokens": 7}')
    assert merged["presence_penalty"] == 1.5 and merged["reasoning_budget_tokens"] == 7
    assert "presence_penalty" not in body_of("--no-extra")
    res = run_cli(tmp_path, monkeypatch, "--scenarios", str(scen), "--no-extra", "--extra", "{}")
    assert res.exit_code != 0


def test_reasoning_effort_comes_from_the_config_even_with_no_extra(tmp_path, monkeypatch):
    scen = write_scenarios(tmp_path / "scen")
    default = tmp_path / "default.yaml"
    monkeypatch.setattr(cr, "DEFAULT_CONFIG", default)

    def sent(*flags):
        seen: list[httpx.Request] = []
        out = tmp_path / f"out{len(list(tmp_path.glob('out*')))}"
        res = run_cli(tmp_path, monkeypatch, "--scenarios", str(scen), "--runs", "1",
                      "--out", str(out), *flags, seen=seen)  # fmt: skip
        assert res.exit_code == 0, res.output
        body = json.loads([r for r in seen if r.url.path.endswith("completions")][0].content)
        settings_ = json.loads((out / "summary.json").read_text())["settings"]
        return body["reasoning_effort"], settings_["reasoning_effort_source"]

    assert sent("--no-extra") == ("medium", "default")
    default.write_text(yaml.safe_dump({"agent": {"reasoning_effort": " High "}}))
    assert sent("--no-extra") == ("high", "config")
    default.chmod(0)
    try:
        assert sent("--no-extra") == ("medium", "default")
    finally:
        default.chmod(0o600)
    other = tmp_path / "other.yaml"
    entry = {"base_url": BASE, "extra_body": {"top_k": 20}}
    other.write_text(
        yaml.safe_dump(
            {
                "model": {"base_url": BASE},
                "custom_providers": [entry],
                "agent": {"reasoning_effort": "low"},
            }
        )  # fmt: skip
    )
    assert sent("--extra-from", str(other)) == ("low", "config")
    assert sent("--extra-from", str(other), "--extra", '{"reasoning_effort": "high"}') == (
        "high",
        "inline",
    )
    assert sent("--extra-from", str(other), "--extra", '{"top_k": 1}') == ("low", "config")
    assert cr.config_effort(None) == ("medium", "default")


EFFORT_CASES = [
    ("high", "high", "config"), (" XHigh ", "xhigh", "config"), ("ultra", "max", "config"),
    (False, "none", "config"), ("false", "none", "config"), ("disabled", "none", "config"),
    ("hgih", "medium", "default"), ("", "medium", "default"), (None, "medium", "default"),
    (True, "medium", "default"), (0, "medium", "default"),
    ({"enabled": False}, "none", "config"), ({"effort": "Bespoke"}, "bespoke", "config"),
    ({"enabled": True}, "medium", "default"),
]  # fmt: skip


@pytest.mark.parametrize(("value", "wire", "source"), EFFORT_CASES)
def test_config_effort_maps_the_value_as_hermes_does(tmp_path, value, wire, source):
    path = tmp_path / "c.yaml"
    path.write_text(yaml.safe_dump({"agent": {"reasoning_effort": value}}))
    assert cr.config_effort(path) == (wire, source)


def test_the_summary_files_hold_none_of_the_texts_and_texts_go_only_where_asked(
    tmp_path, monkeypatch
):
    overlay = {"language": "en", "text": f"Mona app context. {PLANTED['overlay']}"}
    scen = write_scenarios(tmp_path / "scen", overlay=overlay)
    stream = sse(
        {"reasoning_content": PLANTED["reasoning"]},
        {
            "tool_calls": [
                {
                    "index": 0,
                    "function": {"name": "mcp__mona__get_brief", "arguments": PLANTED["args"]},
                }
            ]
        },
        {"content": PLANTED["content"]},
    )

    plain = tmp_path / "plain"
    res = run_cli(
        tmp_path,
        monkeypatch,
        "--scenarios",
        str(scen),
        "--runs",
        "2",
        "--no-extra",
        "--out",
        str(plain),
        chunks=stream,
    )
    assert res.exit_code == 0, res.output
    assert sorted(p.name for p in plain.iterdir()) == ["summary.json", "summary.md"]

    kept = tmp_path / "kept"
    res = run_cli(
        tmp_path,
        monkeypatch,
        "--scenarios",
        str(scen),
        "--runs",
        "1",
        "--no-extra",
        "--keep-text",
        "--out",
        str(kept),
        chunks=stream,
    )
    assert res.exit_code == 0, res.output
    texts = json.loads((kept / "texts" / "s-1.json").read_text())
    assert texts["reasoning"] == PLANTED["reasoning"] and texts["content"] == PLANTED["content"]
    assert texts["tool_calls"][0]["arguments"] == PLANTED["args"]

    for directory in (plain, kept):
        for name in ("summary.json", "summary.md"):
            written = (directory / name).read_text()
            assert not [v for v in PLANTED.values() if v in written], (directory, name)
    assert not [v for v in PLANTED.values() if v in res.output]
    assert json.loads((plain / "summary.json").read_text())["scenarios"]["s"]["n"] == 2


def test_run_refuses_an_out_inside_the_repo_and_keep_text_without_out(tmp_path, monkeypatch):
    scen = write_scenarios(tmp_path / "scen")
    inside = cr.repo_root() / "tmp-replay-out"
    res = run_cli(
        tmp_path, monkeypatch, "--scenarios", str(scen), "--no-extra", "--out", str(inside)
    )
    assert res.exit_code == 2 and not inside.exists()
    res = run_cli(tmp_path, monkeypatch, "--scenarios", str(scen), "--no-extra", "--keep-text")
    assert res.exit_code != 0


def test_the_synthetic_scenarios_are_six_soul_scenarios_without_tools():
    files = sorted(FIXTURES.glob("*.json"))
    assert len(files) == 6
    for f in files:
        s = json.loads(f.read_text())
        assert s["system"] == {"soul": True} and "tools" not in s
        assert s["overlay"]["language"] in {"en", "ro"} and s["user"]
    langs = {f.stem: json.loads(f.read_text())["overlay"]["language"] for f in files}
    assert langs["watched-folder-ro"] == langs["rename-pattern-ro"] == "ro"
    assert cr.load_scenarios(FIXTURES).keys() == {f.stem for f in files}


def _tool_results(spec: dict) -> dict[str, dict]:
    names = {
        c["id"]: c["function"]["name"].removeprefix("mcp__mona__")
        for m in spec["history"]
        for c in m.get("tool_calls") or []
    }
    return {names[m["tool_call_id"]]: json.loads(m["content"]) for m in spec["history"]
            if m["role"] == "tool"}  # fmt: skip


def test_the_synthetic_tool_results_have_c4_shapes():
    load = functools.partial(lambda n: json.loads((FIXTURES / f"{n}.json").read_text()))
    brief = _tool_results(load("mark-paid"))["get_brief"]
    assert set(brief) == {"generated_at", "since", "filed", "needs_review", "due_soon",
                          "reminders_today", "learned", "pending_interview"}  # fmt: skip
    (due,) = brief["due_soon"]
    assert set(due) == {"deadline_id", "label", "entity", "due_date", "days_left", "amount",
                        "currency"}  # fmt: skip
    reply = load("mark-paid")["history"][-1]["content"]
    assert due["label"].removesuffix(" payment demand") in reply and "€212.40" in reply
    reminder = _tool_results(load("what-app"))["schedule_reminder"]
    assert set(reminder) == {"reminder_id", "remind_on", "label", "deadline_id", "document_id",
                             "created", "card_refs"}  # fmt: skip
    preview = _tool_results(load("bare-confirm"))["preview_rule"]
    assert set(preview) == {"rule_id", "name", "state", "condition_text", "moves_total",
                            "stays_total", "moves", "card_refs"}  # fmt: skip
    assert {"document_id", "title", "from", "to"} == set(preview["moves"][0])
    ids = [v for r in (brief, reminder, preview) for v in json.dumps(r).split('"')
           if v[:4] in ("ddl_", "doc_", "rem_", "rul_", "crd_")]  # fmt: skip
    assert ids and all(len(v) == 30 for v in ids)


# --- the host wrapper ---


def wrapper(tmp_path: Path, *args: str, root: Path | None = None) -> subprocess.CompletedProcess:
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    docker = bindir / "docker"
    docker.write_text(f'#!/bin/sh\necho "$*" >> {tmp_path}/calls\n')
    docker.chmod(docker.stat().st_mode | stat.S_IEXEC)
    (tmp_path / "repo").mkdir(exist_ok=True)
    env = {
        "PATH": f"{bindir}:/usr/bin:/bin",
        "HOME": str(tmp_path),
        "MONA_ROOT": str(root or tmp_path / "repo"),
        "MONA_COMPOSE": "docker compose -p t",
        "MONA_UID": "1234",
        "MONA_GID": "1234",
    }
    return subprocess.run(
        [str(WRAPPER), "chat-replay", *args], env=env, capture_output=True, text=True
    )


def test_wrapper_mounts_host_paths_and_refuses_an_out_inside_the_repo(tmp_path):
    (tmp_path / "scen").mkdir()
    cut = tmp_path / "cut.py"
    cut.write_text("")
    out = tmp_path / "private"
    res = wrapper(
        tmp_path,
        "run",
        "--scenarios",
        str(tmp_path / "scen"),
        "--cut",
        str(cut),
        "--extra-from",
        "/hermes/config.yaml",
        "--out",
        str(out),
        "--runs",
        "2",
    )
    assert res.returncode == 0, res.stderr
    call = (tmp_path / "calls").read_text()
    assert "--user 1234:1234" in call and "ops mona chat-replay run" in call
    assert f"-v {tmp_path}/scen:/replay/scenarios:ro" in call
    assert f"-v {out}:/replay/out" in call and "--out /replay/out" in call
    assert f"-v {cut}:/replay/cut/cut.py:ro" in call and "--cut /replay/cut/cut.py" in call
    assert "--extra-from /hermes/config.yaml" in call and "--runs 2" in call

    res = wrapper(
        tmp_path,
        "build",
        "--session",
        "cnv_x",
        "--turn",
        "1",
        "--out",
        str(tmp_path / "repo" / "scen"),
    )
    assert res.returncode != 0 and "inside the repo" in res.stderr
    assert not (tmp_path / "repo" / "scen").exists()


def test_wrapper_edge_cases(tmp_path):
    res = wrapper(tmp_path)
    assert res.returncode == 0, res.stderr
    assert (tmp_path / "calls").read_text().strip().endswith("ops mona chat-replay --help")
    (tmp_path / "calls").unlink()

    for arg in (f"--out={tmp_path}/o", f"--scenarios={tmp_path}"):
        res = wrapper(tmp_path, "run", arg)
        assert res.returncode != 0 and "not --" in res.stderr
    res = wrapper(tmp_path, "run", "--scenarios", str(tmp_path / "missing"))
    assert res.returncode != 0 and "not a directory" in res.stderr
    assert not (tmp_path / "missing").exists()
    res = wrapper(tmp_path, "run", "--out")
    assert res.returncode != 0 and "needs a value" in res.stderr
    assert not (tmp_path / "calls").exists()

    (tmp_path / "repo").mkdir(exist_ok=True)
    link = tmp_path / "link"
    link.symlink_to(tmp_path / "repo")
    res = wrapper(tmp_path, "build", "--out", str(link / "inside"), root=link)
    assert res.returncode != 0 and "inside the repo" in res.stderr
    assert not (tmp_path / "repo" / "inside").exists()

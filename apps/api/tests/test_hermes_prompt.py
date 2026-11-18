"""A57: the `mona_prompt` plugin's cut, its middleware, and the prompt check, on the pinned image's
real prompts (fixtures rendered by tests/hermes_image.py)."""

import importlib.util
import json
import logging
import sqlite3
import sys
from pathlib import Path

import pytest

from mona import hermes_prompt as hp

ROOT = Path(__file__).resolve().parents[3]
PLUGIN = ROOT / "deploy" / "hermes" / "plugins" / "mona_prompt"
PROMPTS = Path(__file__).parent / "fixtures" / "hermes" / "prompts"
CUT = hp.load_cut(PLUGIN / "cut.py")
FIXTURES = sorted(p.stem for p in PROMPTS.glob("*.txt"))
ALWAYS = ["runtime-environment", "hermes-help", "mid-turn-steering", "active-profile"]
BEFORE = ["finishing-the-job", "parallel-tool-calls", "api-server-hint"]


def cut_module():
    spec = importlib.util.spec_from_file_location("mona_prompt_cut_test", PLUGIN / "cut.py")
    module = importlib.util.module_from_spec(spec)
    sys.dont_write_bytecode, saved = True, sys.dont_write_bytecode
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = saved
    return module


def plugin_module():
    name = "hermes_plugins_test.mona_prompt"
    spec = importlib.util.spec_from_file_location(
        name, PLUGIN / "__init__.py", submodule_search_locations=[str(PLUGIN)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    sys.dont_write_bytecode, saved = True, sys.dont_write_bytecode
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = saved
        for key in [k for k in sys.modules if k.startswith(name)]:
            del sys.modules[key]
    return module


def expected_cut(prompt: str) -> str:
    """An independent oracle: the runtime block by index, then each Hermes paragraph by replace."""
    m = cut_module()
    start = prompt.rindex("\n\n" + m.RUNTIME_START)
    end = prompt.index(m.RUNTIME_END, start) + len(m.RUNTIME_END)
    out = prompt[:start] + prompt[end:]
    for _, variants in m.PARAGRAPHS:
        for text in variants:
            out = out.replace("\n\n" + text, "")
    profile = next(c for c in out.split("\n\n") if c.startswith("Active Hermes profile: "))
    return out.replace("\n\n" + profile, "")


def test_the_fixtures_cover_both_configs_wsl_and_the_prompt_before_the_release():
    assert FIXTURES == [
        "before-dev-local", "before-dev-local-wsl", "before-prod-docker", "before-prod-docker-wsl",
        "dev-local", "dev-local-wsl", "prod-docker", "prod-docker-wsl",
    ]  # fmt: skip
    for name in FIXTURES:
        text = (PROMPTS / f"{name}.txt").read_text()
        assert ("/mnt/c/" in text) == name.endswith("-wsl")
        assert ("Terminal backend: docker" in text) == ("docker" in name)
        assert ("# Finishing the job" in text) == name.startswith("before-")


@pytest.mark.parametrize("name", FIXTURES)
def test_the_cut_removes_every_a57_section_and_nothing_else(name):
    prompt = (PROMPTS / f"{name}.txt").read_text()
    assert [m for m in hp.MARKERS if m in prompt]
    text, removed = CUT(prompt)
    assert hp.surviving_markers(prompt, CUT) == []
    assert sorted(removed) == sorted(ALWAYS + (BEFORE if name.startswith("before-") else []))
    assert text == expected_cut(prompt)
    assert text.startswith("# Mona\n\nA fixture SOUL")
    assert "Conversation started: " in text and "Platform: api_server" in text
    assert "Active Hermes profile" not in text and "You run on Hermes Agent" not in text
    assert cut_module().unrecognized(text) == []


@pytest.mark.parametrize("name", ["prod-docker", "prod-docker-wsl", "dev-local-wsl"])
def test_the_release_keeps_mona_s_platform_hint(name):
    text, _ = CUT((PROMPTS / f"{name}.txt").read_text())
    assert text.split("\n\n")[-2] == (
        "You're replying in the Mona web app's chat, which renders Markdown. Keep replies short."
    )


def test_a_prompt_without_hermes_sections_is_left_byte_identical():
    prompt = "# Mona\n\nLine one.\n\n\n\nLine two with # Finishing the job inline.\n"
    assert CUT(prompt) == (prompt, [])
    once, _ = CUT((PROMPTS / "before-prod-docker-wsl.txt").read_text())
    assert CUT(once) == (once, [])


def test_a_shape_the_cut_does_not_know_is_left_whole_and_reported():
    m = cut_module()
    prompt = (PROMPTS / "prod-docker-wsl.txt").read_text()
    no_end = prompt.replace(m.RUNTIME_END, "<!-- End of the runtime environment -->")
    reworded = no_end.replace("Mid-turn, the user can steer you", "Mid-turn, a user may steer you")
    text, removed = CUT(reworded)
    assert "runtime-environment" not in removed and "mid-turn-steering" not in removed
    assert "/mnt/c/" in text and "[OUT-OF-BAND USER MESSAGE" in text
    assert m.unrecognized(text) == ["runtime-environment", "mid-turn-steering"]
    assert sorted(removed) == ["active-profile", "hermes-help"]


def test_a_non_default_profile_paragraph_is_cut():
    para = (
        "Active Hermes profile: work. This session reads and writes /opt/data/profiles/work/. The "
        "default profile's data lives at /opt/data/skills/, /opt/data/plugins/, /opt/data/cron/, "
        "/opt/data/memories/ — those belong to a different session run from a different shell. Do "
        "NOT modify another profile's skills/plugins/cron/memories unless the user explicitly "
        "directs you to."
    )
    assert CUT(f"# Mona\n\n{para}\n\nTail") == ("# Mona\n\nTail", ["active-profile"])


# --- the middleware ---


def request(system) -> dict:
    return {
        "model": "qwen-test",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": "## Mid-turn user steering\nnot a system message"},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "c1"}]},
        ],
        "tools": [{"type": "function", "function": {"name": "mcp__mona__search_documents"}}],
        "extra_body": {"presence_penalty": 1.5},
        "stream": True,
    }


def test_the_middleware_cuts_the_system_message_and_leaves_the_rest_identical():
    plugin = plugin_module()
    prompt = (PROMPTS / "before-prod-docker-wsl.txt").read_text()
    req = request(prompt)
    before = json.dumps(req, sort_keys=True)
    out = plugin.on_llm_request(request=req, original_request=req, session_id="s", platform="x")
    assert json.dumps(req, sort_keys=True) == before
    new = out["request"]
    assert new["messages"][0] == {"role": "system", "content": CUT(prompt)[0]}
    assert new["messages"][1:] == req["messages"][1:]
    assert {k: v for k, v in new.items() if k != "messages"} == {
        k: v for k, v in req.items() if k != "messages"
    }
    assert out["name"] == "mona_prompt" and "runtime-environment" in out["reason"]


def test_the_middleware_cuts_text_parts_and_passes_a_clean_request_through():
    plugin = plugin_module()
    stable, volatile = (PROMPTS / "prod-docker.txt").read_text().split("\n\nConversation started")
    parts = [
        {"type": "text", "text": stable, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": "Conversation started" + volatile},
    ]
    out = plugin.on_llm_request(request=request(parts))["request"]["messages"][0]["content"]
    assert out[0] == {**parts[0], "text": CUT(stable)[0]}
    assert out[1] == {**parts[1], "text": CUT(parts[1]["text"])[0]}
    assert plugin.on_llm_request(request=request("# Mona\n\nNothing of Hermes here.")) is None


def test_an_unknown_request_shape_is_left_whole_with_one_warning(caplog):
    plugin = plugin_module()
    caplog.set_level(logging.WARNING)
    assert plugin.on_llm_request(request={"input": "a responses-style request"}) is None
    assert plugin.on_llm_request(request=request({"unexpected": "shape"})) is None
    assert len([r for r in caplog.records if "mona_prompt" in r.getMessage()]) == 1


def test_the_plugin_registers_one_llm_request_middleware():
    seen = []

    class Ctx:
        def register_middleware(self, kind, callback):
            seen.append((kind, callback.__name__))

    plugin_module().register(Ctx())
    assert seen == [("llm_request", "on_llm_request")]
    manifest = (PLUGIN / "plugin.yaml").read_text()
    assert "name: mona_prompt\n" in manifest and "kind: standalone\n" in manifest
    assert sorted(p.name for p in PLUGIN.iterdir() if p.name != "__pycache__") == [
        "__init__.py", "cut.py", "plugin.yaml",
    ]  # fmt: skip


# --- the prompt check ---


def test_the_prompt_line_names_markers_only():
    secret = "Document text that must never be printed"
    level, name, detail = hp.prompt_line(
        (PROMPTS / "before-prod-docker-wsl.txt").read_text() + secret, lambda t: (t, [])
    )
    assert (level, name) == (hp.RED, "prompt")
    assert "'# Hermes runtime environment'" in detail and "'/mnt/c/'" in detail
    assert secret not in detail and "Mona" not in detail
    level, _, detail = hp.prompt_line((PROMPTS / "before-prod-docker-wsl.txt").read_text(), CUT)
    assert level == hp.GREEN and "finishing-the-job" in detail
    assert hp.prompt_line(None, CUT) == (hp.AMBER, "prompt", "no conversation since the release")
    assert hp.prompt_line("# Mona", None)[0] == hp.RED


@pytest.mark.parametrize(
    ("state", "level", "words"),
    [
        (None, hp.RED, "could not be queried"),
        ({"found": False}, hp.RED, "not installed"),
        ({"found": True, "enabled": False, "failed": False}, hp.RED, "not enabled"),
        ({"found": True, "enabled": False, "failed": True}, hp.RED, "failed to load"),
        ({"found": True, "enabled": True, "failed": False, "middleware": False}, hp.RED, "no llm"),
        ({"found": True, "enabled": True, "failed": False, "middleware": True}, hp.GREEN, "loaded"),
    ],
)
def test_the_plugin_line(state, level, words):
    got = hp.plugin_line(state)
    assert got[:2] == (level, "plugin") and words in got[2]


def state_db(path: Path, rows: list[tuple[str, str, float, str | None]]) -> Path:
    con = sqlite3.connect(path)
    with con:
        con.execute("CREATE TABLE system_prompts (hash TEXT PRIMARY KEY, prompt TEXT NOT NULL)")
        con.execute(
            "CREATE TABLE sessions (id TEXT PRIMARY KEY, source TEXT NOT NULL, system_prompt TEXT,"
            " system_prompt_hash TEXT, started_at REAL NOT NULL)"
        )
        for i, (source, prompt, started, inline) in enumerate(rows):
            con.execute("INSERT OR IGNORE INTO system_prompts VALUES (?, ?)", (f"h{i}", prompt))
            con.execute(
                "INSERT INTO sessions VALUES (?, ?, ?, ?, ?)",
                (f"s{i}", source, inline, None if inline else f"h{i}", started),
            )
    con.close()
    return path


def test_the_newest_web_session_since_the_release_is_read(tmp_path):
    db = state_db(
        tmp_path / "state.db",
        [
            ("api_server", "old web", 100.0, None),
            ("api_server", "new web", 300.0, None),
            ("telegram", "newer telegram", 400.0, None),
        ],
    )
    assert hp.newest_web_prompt(db, since=200.0) == "new web"
    assert hp.newest_web_prompt(db, since=350.0) is None
    assert hp.newest_web_prompt(tmp_path / "missing.db", since=0.0) is None
    legacy = state_db(tmp_path / "legacy.db", [("api_server", "", 10.0, "inline prompt")])
    assert hp.newest_web_prompt(legacy, since=0.0) == "inline prompt"


def test_the_check_opens_the_database_read_only(tmp_path):
    db = state_db(tmp_path / "state.db", [("api_server", "p", 1.0, None)])
    db.chmod(0o444)
    tmp_path.chmod(0o555)
    try:
        assert hp.newest_web_prompt(db, since=0.0) == "p"
        assert sorted(p.name for p in tmp_path.iterdir()) == ["state.db"]
    finally:
        tmp_path.chmod(0o755)


def test_parse_keeps_only_well_formed_lines():
    text = "green\tplugin\tok\nnoise from hermes\namber\tprompt\tno conversation\n"
    assert hp.parse(text) == {"plugin": ("green", "ok"), "prompt": ("amber", "no conversation")}

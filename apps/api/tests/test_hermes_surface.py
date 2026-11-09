import json
from pathlib import Path

import pytest
import yaml

from mona.mcp.server import mcp

ROOT = Path(__file__).resolve().parents[3]
SURFACE = json.loads((Path(__file__).parent / "fixtures" / "hermes" / "surface.json").read_text())
CONFIG = yaml.safe_load((ROOT / "deploy" / "hermes" / "config.yaml").read_text())
UTILITIES = {"list_resources", "read_resource", "list_prompts", "get_prompt"}
TELEGRAM_ONLY = {"ingest_attachment"}
PROD = yaml.safe_load((ROOT / "deploy" / "hermes" / "config.prod.yaml").read_text())


async def test_captured_surface_is_exactly_our_tools_per_platform():
    ours = {t.name for t in await mcp.list_tools()}
    assert SURFACE["platform_toolsets"] == {
        "api_server": ["memory", "mona"],
        "telegram": ["memory", "mona_tg"],
        "cron": ["mona_tg"],
    }
    visible = SURFACE["model_visible_tools"]
    assert set(visible["api_server"]) == {f"mcp__mona__{t}" for t in ours - TELEGRAM_ONLY} | {
        "memory"
    }
    assert set(visible["telegram"]) == {f"mcp__mona_tg__{t}" for t in ours} | {"memory"}
    assert set(visible["cron"]) == {f"mcp__mona_tg__{t}" for t in ours}
    for names in visible.values():
        assert not {n.rsplit("__", 1)[-1] for n in names} & UTILITIES


@pytest.mark.parametrize("config", [CONFIG, PROD], ids=["dev", "prod"])
def test_config_pins_channels_and_turns_off_mcp_extras(config):
    servers = config["mcp_servers"]
    assert {n: s["headers"]["X-Mona-Channel"] for n, s in servers.items()} == {
        "mona": "web",
        "mona_tg": "telegram",
    }
    for s in servers.values():
        assert s["url"] == "http://api:8765/mcp"
        assert s["headers"]["Authorization"] == "Bearer ${MONA_SERVICE_KEY}"
        assert s["sampling"] == {"enabled": False}
    assert servers["mona"]["tools"] == {
        "resources": False,
        "prompts": False,
        "exclude": sorted(TELEGRAM_ONLY),
    }
    assert servers["mona_tg"]["tools"] == {"resources": False, "prompts": False}


def test_hermes_injects_no_model_gated_tool_guidance_in_dev_and_prod():
    for config in (CONFIG, PROD):
        assert config["agent"]["tool_use_enforcement"] is False
        assert config["agent"]["execution_guidance"] is False


def test_config_pins_the_dev_model_and_providers():
    assert CONFIG["tools"]["tool_search"]["enabled"] is False
    assert CONFIG["model"]["default"] == "${MONA_CHAT_MODEL}"
    pins = CONFIG["provider_routing"]["models"]["qwen/qwen3.6-35b-a3b"]
    assert (
        pins["only"]
        == pins["order"]
        == ["akashml", "coreweave", "siliconflow", "parasail", "deepinfra"]
    )
    assert set(CONFIG["provider_routing"]) == {"models"}


def test_profile_seed_ships_empty_cache_dirs_and_no_hand_written_memory():
    seed = ROOT / "deploy" / "hermes"
    assert [p.name for p in (seed / "memories").iterdir()] == ["README.md"]
    for sub in ("documents", "images"):
        assert [p.name for p in (seed / "cache" / sub).iterdir()] == [".gitkeep"]


def test_prod_lockdown_capture_resolves_no_disabled_toolset():
    """C9 §8 test 5, captured on the pinned image with `tests/hermes_lockdown.py`."""
    from mona.privacy import DISABLED_TOOLSETS, PLATFORM_TOOLSETS

    lock = json.loads((Path(__file__).parent / "fixtures" / "hermes" / "lockdown.json").read_text())
    assert lock["disabled_toolsets"] == list(DISABLED_TOOLSETS)
    assert lock["terminal_backend"] == "docker"
    resolved = lock["platform_tools"]
    assert len(resolved) > 3
    for platform, tools in resolved.items():
        assert not set(tools) & set(DISABLED_TOOLSETS), platform
    assert {p: resolved[p] for p in PLATFORM_TOOLSETS} == PLATFORM_TOOLSETS


def test_soul_says_a_card_carries_its_own_content():
    soul = (ROOT / "deploy" / "hermes" / "SOUL.md").read_text()
    principles = soul.split("## Principles", 1)[1].split("\n## ", 1)[0]
    line = next(x for x in principles.splitlines() if x.startswith("- A card carries its own"))
    assert "Introduce it in one line and don't repeat what it shows" in line
    assert "Never invent titles, questions or amounts" in line


def test_soul_steers_a_draft_to_one_search_and_draft_reply():
    soul = (ROOT / "deploy" / "hermes" / "SOUL.md").read_text()
    principles = soul.split("## Principles", 1)[1].split("\n## ", 1)[0]
    line = next(x for x in principles.splitlines() if x.startswith("- Use as few tools"))
    assert "find the letter with one search and call draft_reply with its id straight away" in line


def test_hermes_stops_a_turn_after_8_iterations_in_dev_and_prod():
    assert CONFIG["agent"]["max_turns"] == PROD["agent"]["max_turns"] == 8


def test_soul_lists_what_mona_can_and_cannot_do():
    soul = (ROOT / "deploy" / "hermes" / "SOUL.md").read_text()
    section = soul.split("## What you can do here, and what you can't", 1)[1].split("\n## ", 1)[0]
    lines = section.strip().splitlines()
    can = next(x for x in lines if x.startswith("- You can:"))
    cannot = next(x for x in lines if x.startswith("- You can't:"))
    assert "show a table of documents in the chat, or export it (CSV, Excel, Word)" in can
    assert "IBAN" in can
    assert all(w in cannot for w in ("run programs", "browse", "send anything"))
    assert any("say so in one line and offer the nearest thing" in x for x in lines)
    assert any("budget_exhausted" in x for x in lines)


def test_soul_offers_only_its_tools_and_never_claims_blank_columns():
    soul = (ROOT / "deploy" / "hermes" / "SOUL.md").read_text()
    section = soul.split("## What you can do here, and what you can't", 1)[1].split("\n## ", 1)[0]
    lines = section.strip().splitlines()
    offer = next(x for x in lines if x.startswith("- Offer only what your tools do."))
    assert "IBAN pasted in the chat" in offer
    assert "A draft only knows what you pass it in that call" in offer
    assert any("`empty_columns`" in x and "came out blank" in x for x in lines)
    table = next(x for x in lines if x.startswith('- "A table" means a table in the chat'))
    assert "Never type a table, a header row or a placeholder" in table


def test_hermes_keeps_calling_mona_after_three_failed_calls():
    """A32, captured on the pinned image with `tests/hermes_breaker.py`."""
    calls = json.loads((Path(__file__).parent / "fixtures" / "hermes" / "breaker.json").read_text())
    assert [c["mona_error"] for c in calls] == [
        "invalid_argument",
        "invalid_argument",
        "not_found",
        None,
    ]
    assert all(c["hermes_keys"] == ["result"] for c in calls)
    assert all(c["strikes"] == 0 and not c["breaker_open"] for c in calls)
    assert "filed" in calls[-1]["mona_keys"]

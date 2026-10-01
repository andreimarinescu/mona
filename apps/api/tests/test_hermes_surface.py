import json
from pathlib import Path

import yaml

from mona.mcp.server import mcp

ROOT = Path(__file__).resolve().parents[3]
SURFACE = json.loads((Path(__file__).parent / "fixtures" / "hermes" / "surface.json").read_text())
CONFIG = yaml.safe_load((ROOT / "deploy" / "hermes" / "config.yaml").read_text())
UTILITIES = {"list_resources", "read_resource", "list_prompts", "get_prompt"}


async def test_captured_surface_is_exactly_our_tools_per_platform():
    ours = {t.name for t in await mcp.list_tools()}
    assert SURFACE["platform_toolsets"] == {
        "api_server": ["memory", "mona"],
        "telegram": ["memory", "mona_tg"],
        "cron": ["mona_tg"],
    }
    visible = SURFACE["model_visible_tools"]
    assert set(visible["api_server"]) == {f"mcp__mona__{t}" for t in ours} | {"memory"}
    assert set(visible["telegram"]) == {f"mcp__mona_tg__{t}" for t in ours} | {"memory"}
    assert set(visible["cron"]) == {f"mcp__mona_tg__{t}" for t in ours}
    for names in visible.values():
        assert not {n.rsplit("__", 1)[-1] for n in names} & UTILITIES


def test_config_pins_channels_and_turns_off_mcp_extras():
    servers = CONFIG["mcp_servers"]
    assert {n: s["headers"]["X-Mona-Channel"] for n, s in servers.items()} == {
        "mona": "web",
        "mona_tg": "telegram",
    }
    for s in servers.values():
        assert s["url"] == "http://api:8765/mcp"
        assert s["headers"]["Authorization"] == "Bearer ${MONA_SERVICE_KEY}"
        assert s["sampling"] == {"enabled": False}
        assert s["tools"] == {"resources": False, "prompts": False}
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

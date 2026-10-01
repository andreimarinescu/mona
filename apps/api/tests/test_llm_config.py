"""L6: the prod llama-swap config (plan §3), its rollback copy and the box's llm compose file."""

import re
import shlex
from pathlib import Path

import yaml

from mona.privacy import llm_endpoint_problem

LLM = Path(__file__).resolve().parents[3] / "deploy" / "llm"


def load(name: str) -> dict:
    return yaml.safe_load((LLM / name).read_text())


def command(cfg: dict, model: str) -> list[str]:
    text = cfg["models"][model]["cmd"]
    for key, value in cfg.get("macros", {}).items():
        text = text.replace("${" + key + "}", value)
    return shlex.split(text)


def test_prod_runs_one_35b_server_with_two_64k_slots():
    cfg = load("llama-swap.prod.yaml")
    assert list(cfg["models"]) == ["qwen3.6-35b-a3b"]
    cmd = command(cfg, "qwen3.6-35b-a3b")
    assert cmd[cmd.index("-c") + 1] == "131072"
    assert cmd[cmd.index("--parallel") + 1] == "2"
    assert "--n-cpu-moe" in cmd and "--jinja" in cmd
    assert cmd[cmd.index("--cache-type-k") + 1] == "q8_0"
    assert cfg["models"]["qwen3.6-35b-a3b"]["ttl"] == 0


def test_prod_has_no_4b_no_vision_and_no_baked_thinking_switch():
    text = (LLM / "llama-swap.prod.yaml").read_text()
    assert "4B" not in text and "qwen3.5" not in text
    assert "mmproj" not in text
    assert "enable_thinking" not in text


def test_the_agent_group_holds_only_defined_models_and_macros_are_all_defined():
    cfg = load("llama-swap.prod.yaml")
    assert set(cfg["groups"]["agent"]["members"]) == set(cfg["models"])
    used = set(re.findall(r"\$\{(\w+)\}", cfg["models"]["qwen3.6-35b-a3b"]["cmd"])) - {"PORT"}
    assert used == set(cfg["macros"])


def test_the_two_lane_rollback_copy_still_has_all_four_lanes():
    cfg = load("llama-swap.two-lane.yaml")
    assert set(cfg["models"]) == {
        "qwen3.5-4b", "qwen3-30b-a3b", "qwen3.6-35b-a3b", "qwen3.6-35b-a3b-nothink",
    }  # fmt: skip
    assert "--n-cpu-moe 28" in cfg["models"]["qwen3.6-35b-a3b"]["cmd"]


def test_llama_swap_joins_the_compose_network_and_is_never_published_beyond_loopback():
    svc = load("compose.prod.yaml")["services"]["llm"]
    assert svc["networks"]["mona"]["aliases"] == ["llama-swap"]
    assert all(p.startswith("127.0.0.1:") for p in svc["ports"])
    assert svc["entrypoint"][-1] == ":8080"
    assert llm_endpoint_problem("http://llama-swap:8080/v1") is None

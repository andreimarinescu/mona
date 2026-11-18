"""The chat request the pinned image builds for a web turn: Mona's MCP tools registered through
Hermes' own path, then `build_api_kwargs`. Input on stdin: {"tools": [{name, description,
inputSchema}]}; the config is mounted at /in/config.yaml (see tests/hermes_replay.py)."""

import json
import os
import shutil
import sys

tools = json.loads(sys.stdin.read())["tools"]
shutil.copy("/in/config.yaml", "/opt/data/config.yaml")
with open("/opt/data/SOUL.md", "w") as f:
    f.write("# Mona\n")
sys.path.insert(0, "/opt/hermes")
os.chdir("/opt/hermes")

import gateway.run as gr  # noqa: E402
from agent.chat_completion_helpers import build_api_kwargs  # noqa: E402
from hermes_cli.config import load_config  # noqa: E402
from hermes_cli.tools_config import _get_platform_tools  # noqa: E402
from run_agent import AIAgent  # noqa: E402
from tools import mcp_tool_registration as reg  # noqa: E402

cfg = load_config()
keep = reg._make_tool_filter("mona", cfg["mcp_servers"]["mona"])
candidates = reg._tool_candidates("mona", reg._cached_tools(tools), keep, 30)
reg._register_candidates("mona", candidates, check_fn=None, scope=lambda: None, lazy=False)
runtime = gr._resolve_runtime_agent_kwargs()
runtime.pop("_fallback_notice", None)
model = runtime.pop("model", None) or gr._resolve_gateway_model()
agent = AIAgent(
    model=model, **runtime, quiet_mode=True, platform="api_server",
    enabled_toolsets=sorted(_get_platform_tools(cfg, "api_server")),
    session_id="20261118_120000_replay",
)  # fmt: skip
messages = [{"role": "system", "content": "S"}, {"role": "user", "content": "U"}]
kwargs = build_api_kwargs(agent, messages, agent.tools)
print(json.dumps({k: v for k, v in kwargs.items() if k not in ("messages", "timeout")}))

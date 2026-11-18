"""A57 render with no turn, run on the pinned image: the system prompt Hermes' api_server builds.

docker run --rm -i --network none --tmpfs /opt/data -v <config>:/in/config.yaml:ro \
  -v <SOUL>:/in/SOUL.md:ro [-e RENDER_WSL=1] --entrypoint /opt/hermes/.venv/bin/python <image> - \
  < apps/api/tests/hermes_render.py
"""

import json
import os
import shutil
import sys

for name in ("config.yaml", "SOUL.md"):
    shutil.copy(f"/in/{name}", f"/opt/data/{name}")
sys.path.insert(0, "/opt/hermes")
os.chdir("/opt/hermes")

if os.environ.get("RENDER_WSL") == "1":
    import agent.prompt_builder as pb  # noqa: E402

    pb.is_wsl = lambda: True

import gateway.run as gr  # noqa: E402
from agent.system_prompt import build_system_prompt  # noqa: E402
from hermes_cli.config import load_config  # noqa: E402
from hermes_cli.tools_config import _get_platform_tools  # noqa: E402
from run_agent import AIAgent  # noqa: E402

cfg = load_config()
runtime = gr._resolve_runtime_agent_kwargs()
runtime.pop("_fallback_notice", None)
model = runtime.pop("model", None) or gr._resolve_gateway_model()
agent = AIAgent(
    model=model, **runtime, quiet_mode=True, platform="api_server",
    enabled_toolsets=sorted(_get_platform_tools(cfg, "api_server")),
    session_id="20261118_120000_render",
)  # fmt: skip
prompt = build_system_prompt(agent)
print(
    json.dumps({"prompt": prompt, "extra_body": (agent.request_overrides or {}).get("extra_body")})
)

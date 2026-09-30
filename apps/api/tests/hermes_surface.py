"""C4 §5.2 capture, run inside the Hermes container against the live api:

docker compose exec -T hermes /opt/hermes/.venv/bin/python - < apps/api/tests/hermes_surface.py
"""

import json
import os
import sys

sys.path.insert(0, "/opt/hermes")
os.chdir("/opt/hermes")

from hermes_cli.config import load_config  # noqa: E402
from hermes_cli.tools_config import _get_platform_tools  # noqa: E402
from model_tools import get_tool_definitions  # noqa: E402
from tools.mcp_tool_discovery import discover_mcp_tools  # noqa: E402

cfg = load_config()
platforms = {p: sorted(_get_platform_tools(cfg, p)) for p in ("api_server", "telegram", "cron")}
discover_mcp_tools()
visible = {
    p: sorted(
        d["function"]["name"] for d in get_tool_definitions(enabled_toolsets=ts, quiet_mode=True)
    )
    for p, ts in platforms.items()
}
print(json.dumps({"platform_toolsets": platforms, "model_visible_tools": visible}, indent=2))

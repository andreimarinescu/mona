"""A32 capture: three failing calls, then a valid one, through Hermes' own MCP client and breaker.

docker compose exec -T hermes /opt/hermes/.venv/bin/python - < apps/api/tests/hermes_breaker.py
"""

import json
import os
import sys

sys.path.insert(0, "/opt/hermes")
os.chdir("/opt/hermes")

from tools import mcp_tool as core  # noqa: E402
from tools.mcp_tool_discovery import discover_mcp_tools  # noqa: E402
from tools.mcp_tool_scope import _resolve_server_key  # noqa: E402
from tools.registry import registry  # noqa: E402

CALLS = [
    ("search_documents", {"limit": 99}),
    ("search_documents", {"category": "payable"}),
    ("get_document", {"document_id": "doc_" + "0" * 26}),
    ("get_brief", {}),
]

discover_mcp_tools()
key = _resolve_server_key("mona")
out = []
for name, args in CALLS:
    raw = registry.dispatch(f"mcp__mona__{name}", args)
    seen = json.loads(raw) if isinstance(raw, str) else raw
    inner = seen.get("result")
    body = json.loads(inner) if isinstance(inner, str) and inner.startswith("{") else {}
    out.append(
        {
            "tool": name,
            "hermes_keys": sorted(seen),
            "mona_error": (body.get("error") or {}).get("code"),
            "mona_keys": sorted(body),
            "strikes": core._server_error_counts.get(key, 0),
            "breaker_open": key in core._server_breaker_opened_at,
        }
    )
print(json.dumps(out, indent=2))

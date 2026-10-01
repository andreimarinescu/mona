"""FastMCP at `/mcp` behind the service key (C4 §1)."""

import hmac
import logging

from starlette.types import ASGIApp, Receive, Scope, Send

from mona.http import refuse
from mona.interviews import tools as _interview_tools  # noqa: F401
from mona.mcp import read as _read  # noqa: F401  (registers the tools)
from mona.mcp.core import mcp
from mona.settings import get_settings
from mona.workflow import tools as _workflow_tools  # noqa: F401

logger = logging.getLogger(__name__)

MIN_KEY_LENGTH = 32
MAX_MCP_BODY = 64 * 1024


class ServiceKeyAuth:
    """401 before any MCP handling unless `Authorization: Bearer $MONA_SERVICE_KEY`."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        key = get_settings().mona_service_key
        secret = key.get_secret_value() if key else ""
        given = dict(scope.get("headers") or []).get(b"authorization", b"")
        expected = f"Bearer {secret}".encode()
        if len(secret) < MIN_KEY_LENGTH or not hmac.compare_digest(given, expected):
            client = scope.get("client") or ("?", 0)
            logger.warning("mcp: unauthorized request from %s", client[0])
            await refuse(send, 401, {"error": "unauthorized"})
            return
        await self.app(scope, receive, send)


def build_mcp_app():
    return mcp.http_app(path="/mcp", stateless_http=True)

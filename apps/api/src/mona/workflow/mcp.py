"""Running the sync services from MCP tools: a worker thread, C4 §2.4 errors."""

from functools import partial
from typing import Any

import anyio

from mona.mcp.core import ToolFailure
from mona.services import ServiceError


async def run(fn: Any, *args: Any, **kwargs: Any) -> Any:
    try:
        return await anyio.to_thread.run_sync(partial(fn, *args, **kwargs))
    except ServiceError as err:
        raise ToolFailure(
            err.code, err.message, hint=err.hint, field=err.field, valid=err.valid
        ) from None


def via(channel: str) -> str:
    return "chat" if channel == "web" else "telegram"

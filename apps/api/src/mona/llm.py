"""C9 §1.2 fail-closed guard for typed model calls, for the one model client to use.

`endpoint(settings)` is the base URL the client must use; `guarded_http_client(settings)` refuses,
before any connection, a request to any other host when `MONA_ENV=prod`."""

from typing import Any

import httpx

from mona.privacy import ModelEndpoint, guard_model_url, model_endpoint
from mona.settings import Settings, get_settings

__all__ = ["ModelEndpoint", "endpoint", "guarded_http_client"]


def endpoint(settings: Settings | None = None) -> ModelEndpoint:
    """Prod: the checked local URL (raises `ProdCheckFailed` otherwise); dev: the configured
    URL, else OpenRouter."""
    return model_endpoint(settings or get_settings())


def guarded_http_client(settings: Settings | None = None, **kwargs: Any) -> httpx.AsyncClient:
    s = settings or get_settings()
    endpoint(s)

    async def check(request: httpx.Request) -> None:
        guard_model_url(str(request.url), s)

    hooks = kwargs.pop("event_hooks", {})
    hooks["request"] = [check, *hooks.get("request", [])]
    return httpx.AsyncClient(event_hooks=hooks, **kwargs)

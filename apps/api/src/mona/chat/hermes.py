"""Thin client for the Hermes API server (D3: completions path + session endpoints)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Any

import httpx

from mona.settings import get_settings

TIMEOUT = httpx.Timeout(connect=5.0, read=120.0, write=30.0, pool=5.0)


class HermesError(Exception):
    """Hermes could not be reached, or refused the request before streaming."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class HermesClient:
    def __init__(
        self, base_url: str, api_key: str, transport: httpx.AsyncBaseTransport | None = None
    ):
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=TIMEOUT,
            transport=transport,
        )

    async def create_session(self, title: str) -> str:
        """Hermes session titles must be unique; callers pass the conversation id."""
        try:
            res = await self._client.post("/api/sessions", json={"title": title})
        except httpx.HTTPError as e:
            raise HermesError("hermes_unreachable") from e
        if res.status_code >= 400:
            raise HermesError(f"hermes_http_{res.status_code}")
        return res.json()["session"]["id"]

    async def session_messages(self, session_id: str) -> list[dict[str, Any]]:
        res = await self._client.get(f"/api/sessions/{session_id}/messages")
        res.raise_for_status()
        return res.json()["data"]

    @asynccontextmanager
    async def stream_completion(
        self, session_id: str, messages: list[dict[str, str]]
    ) -> AsyncIterator[AsyncIterator[str]]:
        """Yields the upstream SSE lines; raises HermesError before the first line."""
        req = self._client.build_request(
            "POST",
            "/v1/chat/completions",
            headers={"X-Hermes-Session-Id": session_id},
            json={"model": "mona", "stream": True, "messages": messages},
        )
        try:
            res = await self._client.send(req, stream=True)
        except httpx.HTTPError as e:
            raise HermesError("hermes_unreachable") from e
        try:
            if res.status_code >= 400:
                raise HermesError(f"hermes_http_{res.status_code}")
            yield res.aiter_lines()
        finally:
            await res.aclose()


@lru_cache
def get_hermes() -> HermesClient:
    s = get_settings()
    key = s.hermes_api_key.get_secret_value() if s.hermes_api_key else ""
    return HermesClient(s.hermes_url, key)

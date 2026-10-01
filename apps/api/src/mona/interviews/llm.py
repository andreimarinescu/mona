"""The interview and draft calls on the one model client (C9 §1.2, D11): `mona.pipeline.model`."""

import asyncio
import time
from collections.abc import Iterator
from typing import Any

import httpx
from openai import APIError
from pydantic_ai import Agent, NativeOutput, StructuredDict
from pydantic_ai.exceptions import ModelAPIError, UnexpectedModelBehavior

from mona.interviews.model import Delta, ModelError
from mona.pipeline import model as client
from mona.settings import Settings, get_settings


def thinking_body(backend: str, model: str) -> dict[str, Any]:
    """The client's knobs with thinking on (C6 §4.1's one `thinking` flag)."""
    if backend == "llama-server":
        return {"chat_template_kwargs": {"enable_thinking": True}}
    return {**client.extra_body(backend, model), "reasoning": {"enabled": True}}


def _delta_text(delta: Any, *names: str) -> str:
    extra = getattr(delta, "model_extra", None) or {}
    for name in names:
        value = getattr(delta, name, None) or extra.get(name)
        if value:
            return value
    return ""


class InterviewClient(client.LlmClient):
    """`LlmClient` plus a streamed thinking call (pass 1) and a named strict-schema call."""

    def stream(
        self, system: str, user: str, *, temperature: float, max_tokens: int, timeout_s: float
    ) -> Iterator[Delta]:
        """Ends quietly at `timeout_s` from the request, even while the stream is silent."""
        deadline = time.monotonic() + timeout_s
        with self._lock:
            try:
                chunks = self._loop.run_until_complete(
                    self._chat.client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        stream=True,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        timeout=timeout_s,
                        extra_body=thinking_body(self.backend, self.model),
                    )
                )
            except (APIError, httpx.HTTPError, TimeoutError) as e:
                raise ModelError(type(e).__name__) from e
            it = chunks.__aiter__()
            try:
                while (left := deadline - time.monotonic()) > 0:
                    try:
                        chunk = self._loop.run_until_complete(
                            asyncio.wait_for(it.__anext__(), left)
                        )
                    except (StopAsyncIteration, TimeoutError):
                        return
                    except (APIError, httpx.HTTPError) as e:
                        raise ModelError(type(e).__name__) from e
                    for choice in chunk.choices or []:
                        reasoning = _delta_text(choice.delta, "reasoning", "reasoning_content")
                        if reasoning:
                            yield "reasoning", reasoning
                        if choice.delta.content:
                            yield "content", choice.delta.content
            finally:
                self._loop.run_until_complete(chunks.close())

    def complete_json(
        self,
        system: str,
        user: str,
        schema: dict[str, Any],
        *,
        name: str,
        temperature: float,
        max_tokens: int,
        timeout_s: float,
    ) -> dict[str, Any]:
        settings = {
            **client.model_settings(self.backend, self.model),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "timeout": timeout_s,
        }
        agent = Agent(
            self._chat,
            output_type=NativeOutput(StructuredDict(schema, name=name), strict=True),
            instructions=system,
            retries=0,
        )
        with self._lock:
            try:
                result = self._loop.run_until_complete(
                    agent.run(user, model_settings=settings)  # type: ignore[arg-type]
                )
            except UnexpectedModelBehavior as e:
                raise ModelError("schema") from e
            except (ModelAPIError, httpx.HTTPError, TimeoutError) as e:
                raise ModelError(type(e).__name__) from e
        if not isinstance(result.output, dict):
            raise ModelError("schema")
        return result.output


def from_settings(s: Settings | None = None) -> InterviewClient:
    return InterviewClient.from_settings(s or get_settings())  # type: ignore[return-value]

"""C5 §5.1 model client: strict json_schema through pydantic-ai `NativeOutput`, thinking off."""

import asyncio
import os
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Literal, Protocol

import httpx
from openai import APIError
from pydantic_ai import Agent, NativeOutput, StructuredDict
from pydantic_ai.exceptions import ModelAPIError, UnexpectedModelBehavior
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.profiles.openai import OpenAIModelProfile
from pydantic_ai.providers.openai import OpenAIProvider

from mona import llm
from mona.pipeline import schema as output_schema
from mona.settings import Settings

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

OPENROUTER_URL = "https://openrouter.ai/api/v1"
QWEN36 = "qwen/qwen3.6-35b-a3b"
D4_PIN = {
    "order": ["akashml", "coreweave", "siliconflow", "parasail", "deepinfra"],
    "allow_fallbacks": False,
    "require_parameters": True,
    "quantizations": ["fp8", "fp16", "bf16"],
}
TEMPERATURE = 0
MAX_TOKENS = 2000
TIMEOUT_S = 90
SCHEMA_NAME = "mona_extraction"


class TransportError(Exception):
    """The request failed or timed out; retried (C5 §1.2)."""


class SchemaInvalid(Exception):
    """The output isn't valid against this request's schema; retried (C5 §1.2)."""


@dataclass(frozen=True)
class ModelResult:
    raw: dict[str, Any]
    duration_ms: int
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


Delta = tuple[Literal["reasoning", "content"], str]


class ModelClient(Protocol):
    model: str

    def complete(self, system: str, user: str, schema: dict[str, Any]) -> ModelResult: ...


def extra_body(backend: str, model: str) -> dict[str, Any]:
    """Each backend's thinking-off knob; the D4 pins only for Qwen 3.6 on OpenRouter (D9)."""
    if backend == "llama-server":
        return {"chat_template_kwargs": {"enable_thinking": False}}
    body: dict[str, Any] = {"reasoning": {"enabled": False}}
    if model == QWEN36:
        body["provider"] = D4_PIN
    return body


def thinking_body(backend: str, model: str) -> dict[str, Any]:
    """The same knobs with thinking on (C6 §4.1)."""
    if backend == "llama-server":
        return {"chat_template_kwargs": {"enable_thinking": True}}
    return {**extra_body(backend, model), "reasoning": {"enabled": True}}


def _delta_text(delta: Any, *names: str) -> str:
    extra = getattr(delta, "model_extra", None) or {}
    for name in names:
        value = getattr(delta, name, None) or extra.get(name)
        if value:
            return value
    return ""


def model_settings(backend: str, model: str) -> dict[str, Any]:
    return {"temperature": TEMPERATURE, "max_tokens": MAX_TOKENS, "timeout": TIMEOUT_S,
            "extra_body": extra_body(backend, model)}  # fmt: skip


PROFILE = OpenAIModelProfile(
    supports_json_schema_output=True,
    json_schema_transformer=None,  # the default moves maxLength into descriptions
    openai_chat_supports_max_completion_tokens=False,
)


class LlmClient:
    """One OpenAI-compatible client for OpenRouter and llama-server; sync, on its own loop."""

    def __init__(
        self,
        *,
        model: str,
        backend: str = "openrouter",
        base_url: str | None = None,
        api_key: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ):
        if model.endswith(":free"):
            raise ValueError("free endpoints are never used (D9)")
        if backend == "llama-server" and not base_url:
            raise ValueError("MONA_LLM_BASE_URL is required for llama-server")
        self.model = model
        self.backend = backend
        self._loop = asyncio.new_event_loop()
        self._lock = threading.Lock()
        kw: dict[str, Any] = {"http_client": http_client} if http_client else {}
        provider = OpenAIProvider(
            base_url=base_url or OPENROUTER_URL, api_key=api_key or "none", **kw
        )
        self._chat = OpenAIChatModel(model, provider=provider, profile=PROFILE)

    @classmethod
    def from_settings(cls, s: Settings) -> "LlmClient":
        """C9 §1.2: endpoint and transport from `mona.llm`, which fail closed in prod."""
        key = s.openrouter_api_key.get_secret_value() if s.openrouter_api_key else None
        endpoint = llm.endpoint(s)
        return cls(
            model=s.mona_llm_model, backend=s.mona_llm_backend,
            base_url=endpoint.base_url if endpoint.local else None,
            api_key=key if s.mona_llm_backend == "openrouter" else None,
            http_client=llm.guarded_http_client(s),
        )  # fmt: skip

    def complete(self, system: str, user: str, schema: dict[str, Any]) -> ModelResult:
        with self._lock:
            return self._loop.run_until_complete(self._complete(system, user, schema))

    async def _complete(self, system: str, user: str, schema: dict[str, Any]) -> ModelResult:
        agent = Agent(
            self._chat,
            output_type=NativeOutput(StructuredDict(schema, name=SCHEMA_NAME), strict=True),
            instructions=system,
            retries=0,
        )
        start = time.monotonic()
        try:
            result = await agent.run(user, model_settings=model_settings(self.backend, self.model))
        except UnexpectedModelBehavior as e:
            raise SchemaInvalid(type(e).__name__) from e
        except (ModelAPIError, httpx.HTTPError, TimeoutError) as e:
            raise TransportError(type(e).__name__) from e
        raw = result.output
        if not isinstance(raw, dict) or output_schema.errors(raw, schema):
            raise SchemaInvalid("schema")
        usage = result.usage
        return ModelResult(raw, int((time.monotonic() - start) * 1000), usage.input_tokens,
                           usage.output_tokens)  # fmt: skip

    def stream(
        self, system: str, user: str, *, temperature: float, max_tokens: int, timeout_s: float
    ) -> Iterator[Delta]:
        """Thinking on, streamed; ends quietly at `timeout_s`, even mid-silence."""
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
                raise TransportError(type(e).__name__) from e
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
                        raise TransportError(type(e).__name__) from e
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
        """Thinking off, a named strict json_schema; raises TransportError or SchemaInvalid."""
        settings = {
            **model_settings(self.backend, self.model),
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
                raise SchemaInvalid("schema") from e
            except (ModelAPIError, httpx.HTTPError, TimeoutError) as e:
                raise TransportError(type(e).__name__) from e
        if not isinstance(result.output, dict):
            raise SchemaInvalid("schema")
        return result.output

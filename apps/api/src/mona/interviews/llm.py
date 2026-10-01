"""The interview and draft calls on the one model client (C9 §1.2, D11): `mona.pipeline.model`."""

from collections.abc import Iterator
from typing import Any

from mona.interviews.model import Delta, ModelError
from mona.pipeline.model import LlmClient, SchemaInvalid, TransportError
from mona.settings import Settings, get_settings


class InterviewModel:
    """`LanguageModel` over `LlmClient`'s public calls; their failures become `ModelError`."""

    def __init__(self, client: LlmClient):
        self.client = client
        self.model = client.model

    def stream(
        self, system: str, user: str, *, temperature: float, max_tokens: int, timeout_s: float
    ) -> Iterator[Delta]:
        try:
            yield from self.client.stream(
                system, user, temperature=temperature, max_tokens=max_tokens, timeout_s=timeout_s
            )
        except (TransportError, SchemaInvalid) as e:
            raise ModelError(str(e)) from e

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
        try:
            return self.client.complete_json(
                system,
                user,
                schema,
                name=name,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout_s=timeout_s,
            )
        except (TransportError, SchemaInvalid) as e:
            raise ModelError(str(e)) from e


def from_settings(s: Settings | None = None) -> InterviewModel:
    return InterviewModel(LlmClient.from_settings(s or get_settings()))

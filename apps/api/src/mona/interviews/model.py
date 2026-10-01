"""What the interview and draft jobs need from the one model client (C9 §1.2, D11)."""

from collections.abc import Callable, Iterator
from typing import Any, Literal, Protocol

Delta = tuple[Literal["reasoning", "content"], str]


class ModelError(Exception):
    """A transport failure or an output that doesn't match the schema; retried once (C6 §4.4)."""


class ModelUnavailable(ModelError):
    pass


class LanguageModel(Protocol):
    model: str

    def stream(
        self, system: str, user: str, *, temperature: float, max_tokens: int, timeout_s: float
    ) -> Iterator[Delta]:
        """Thinking on, streamed: reasoning and content deltas as they arrive."""
        ...

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
        """Thinking off, strict json_schema; raises ModelError."""
        ...


_factory: Callable[[], LanguageModel] | None = None


def set_model_factory(factory: Callable[[], LanguageModel] | None) -> None:
    global _factory
    _factory = factory


def get_model() -> LanguageModel:
    """The bound factory's model, else `mona.interviews.llm` on the pipeline's client."""
    if _factory is not None:
        return _factory()
    try:
        from mona.interviews.llm import from_settings
    except ImportError as e:
        raise ModelUnavailable("no model client is configured") from e
    return from_settings()

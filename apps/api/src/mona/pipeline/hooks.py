"""The context hooks of the api and the workers: C6 §3.1's `mona.interviews.hooks`."""

from collections.abc import Callable


def _on_batch_done(batch_id: str) -> None:
    from mona.interviews import hooks

    hooks.on_batch_done(batch_id)


def _on_document_settled(batch_id: str) -> None:
    from mona.interviews import hooks

    hooks.on_document_settled(batch_id)


def interview_hooks() -> dict[str, Callable[[str], None]]:
    """`make_context` keyword arguments wiring the C6 hooks."""
    return {"on_batch_done": _on_batch_done, "on_document_settled": _on_document_settled}

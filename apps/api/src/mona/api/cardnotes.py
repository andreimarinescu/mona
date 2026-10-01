"""C2 §14 card-action notes written by REST actions (C3 §6), synchronously."""

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Connection, insert, select

from mona.chat.notes import TEXT_MAX, note_value
from mona.services.registry import T


@dataclass
class PendingNote:
    conversation_id: str
    written: bool = False


_pending: ContextVar[PendingNote | None] = ContextVar("pending_undo_note", default=None)


def conversation_exists(conn: Connection, conversation_id: str | None) -> bool:
    if conversation_id is None:
        return False
    c = T["conversations"]
    return conn.execute(select(c.c.id).where(c.c.id == conversation_id)).first() is not None


def write(conn: Connection, conversation_id: str, kind: str, text: str) -> None:
    from mona.ids import new_id

    conn.execute(
        insert(T["card_action_notes"]).values(
            id=new_id("not"), conversation_id=conversation_id, kind=kind, text=text[:TEXT_MAX]
        )
    )


def place(state: Mapping[str, Any] | None) -> str:
    if not state:
        return "its previous place"
    if state.get("location") == "inbox":
        return "the Inbox"
    if state.get("location") == "trash":
        return "the trash"
    return state["path"].rpartition("/")[0] or "the archive"


def undo_entry_text(title: str, state: Mapping[str, Any] | None) -> str:
    return f"Undid 1 change(s): {note_value(f'{title} back to {place(state)}')}."


def undo_group_text(n: int, summary: str) -> str:
    return f"Undid {n} change(s): {note_value(summary)}."


def rule_apply_text(name: str, moved: int, unchanged: int) -> str:
    return (
        f'Applied the rule "{note_value(name)}": {moved} documents moved, '
        f"{unchanged} already in place."
    )


@contextmanager
def undo_note(conversation_id: str | None) -> Iterator[PendingNote | None]:
    """While set, the step C of this single undo also writes the note (§14: same transaction
    as the effect)."""
    if conversation_id is None:
        yield None
        return
    note = PendingNote(conversation_id)
    token = _pending.set(note)
    try:
        yield note
    finally:
        _pending.reset(token)


def commit_hook(inner: Callable[..., None] | None) -> Callable[..., None]:
    """Wraps the file-ops step C hook to add a pending undo note in the same transaction."""

    def hook(conn: Connection, e: Mapping[str, Any], doc: Mapping[str, Any]) -> None:
        if inner is not None:
            inner(conn, e, doc)
        note = _pending.get()
        if note is None or note.written or e["undo_of"] is None:
            return
        if not conversation_exists(conn, note.conversation_id):
            return
        title = doc["title"] or doc["original_name"]
        write(conn, note.conversation_id, "undo", undo_entry_text(title, e["after"]))
        note.written = True

    return hook

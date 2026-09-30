"""Card-action notes (C3 §6): texts, and their consume/release around a turn."""

from datetime import date

from sqlalchemy import insert, update
from sqlalchemy.ext.asyncio import AsyncConnection

from mona.chat.overlay import single_line
from mona.db.models import CardActionNote
from mona.ids import new_id

VALUE_MAX = 80
TEXT_MAX = 300


def note_value(value: str) -> str:
    """A document- or model-sourced value: one line, `"` → `'`, ≤ 80 chars at a word boundary."""
    value = single_line(value).replace('"', "'")
    if len(value) <= VALUE_MAX:
        return value
    cut = value[: VALUE_MAX - 1]
    head = cut.rsplit(" ", 1)[0] if " " in cut else cut
    return head.rstrip() + "…"


def interview_answer(question: str, option: str, rule_names: list[str]) -> str:
    text = f'Answered interview question "{note_value(question)}" with "{note_value(option)}".'
    if rule_names:
        quoted = ", ".join(f'"{note_value(n)}"' for n in rule_names)
        text += f" {len(rule_names)} rule(s) drafted: {quoted}"
    return text


def rule_apply(rule_name: str, moved: int, unchanged: int) -> str:
    return (
        f'Applied the rule "{note_value(rule_name)}": {moved} documents moved, '
        f"{unchanged} already in place."
    )


def undo(n: int, summary: str) -> str:
    return f"Undid {n} change(s): {note_value(summary)}."


def reminder_add(label: str, on: date) -> str:
    return f'Set a reminder for "{note_value(label)}" on {on.isoformat()}.'


def draft_download(title: str) -> str:
    return f'Downloaded the draft "{note_value(title)}".'


async def add_note(conn: AsyncConnection, conversation_id: str, kind: str, text: str) -> str:
    note_id = new_id("not")
    await conn.execute(
        insert(CardActionNote).values(
            id=note_id, conversation_id=conversation_id, kind=kind, text=text[:TEXT_MAX]
        )
    )
    return note_id


async def consume(conn: AsyncConnection, conversation_id: str, turn_id: str) -> list[str]:
    """All pending notes of the conversation, now owned by `turn_id`; oldest first."""
    rows = (
        await conn.execute(
            update(CardActionNote)
            .where(
                CardActionNote.conversation_id == conversation_id,
                CardActionNote.consumed_turn_id.is_(None),
            )
            .values(consumed_turn_id=turn_id)
            .returning(CardActionNote.text, CardActionNote.created_at, CardActionNote.id)
        )
    ).all()
    return [r.text for r in sorted(rows, key=lambda r: (r.created_at, r.id))]


async def release(conn: AsyncConnection, turn_id: str) -> None:
    await conn.execute(
        update(CardActionNote)
        .where(CardActionNote.consumed_turn_id == turn_id)
        .values(consumed_turn_id=None)
    )

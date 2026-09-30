from datetime import UTC, datetime, timedelta

import psycopg
from psycopg.rows import namedtuple_row

from mona.ids import new_id
from mona.settings import get_settings


def add_turn(status: str = "open", expires_in_s: int = 120, conversation_id: str | None = None):
    """Insert a conversation (unless given) and a turn; returns (conversation_id, turn_id)."""
    cid = conversation_id or new_id("cnv")
    tid = new_id("trn")
    with psycopg.connect(get_settings().libpq_url) as conn:
        if conversation_id is None:
            conn.execute(
                "INSERT INTO spike_conversations (id, hermes_session_id, title)"
                " VALUES (%s, %s, 't')",
                (cid, f"sess-{cid}"),
            )
        ordinal = conn.execute(
            "SELECT count(*) + 1 FROM spike_chat_turns WHERE conversation_id = %s", (cid,)
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO spike_chat_turns (id, conversation_id, status, user_ordinal,"
            " ui_message_id, reply_language, lease_expires_at)"
            " VALUES (%s, %s, %s, %s, %s, 'en', %s)",
            (
                tid,
                cid,
                status,
                ordinal,
                new_id("msg"),
                datetime.now(UTC) + timedelta(seconds=expires_in_s),
            ),
        )
    return cid, tid


def card_rows():
    with psycopg.connect(get_settings().libpq_url, row_factory=namedtuple_row) as conn:
        return conn.execute(
            "SELECT id, tool, kind, subject, turn_id, emitted_at FROM spike_card_events"
            " ORDER BY created_at"
        ).fetchall()


def turn_row(turn_id: str):
    with psycopg.connect(get_settings().libpq_url, row_factory=namedtuple_row) as conn:
        return conn.execute(
            "SELECT status, error_code, reasoning_ms, finish_reason FROM spike_chat_turns"
            " WHERE id = %s",
            (turn_id,),
        ).fetchone()

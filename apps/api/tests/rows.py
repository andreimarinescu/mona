"""Synthetic rows for chat and MCP tests, written straight to the current test database."""

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from typing import Any

import psycopg
from psycopg.rows import namedtuple_row

from mona.ids import new_id
from mona.settings import get_settings
from mona.text import norm

CLEANUP = [
    "DELETE FROM conversations",
    "DELETE FROM card_events",
    "UPDATE documents SET filed_op_id = NULL",
    "DELETE FROM file_ops",
    "DELETE FROM op_groups",
    "DELETE FROM reminders",
    "DELETE FROM deadlines",
    "DELETE FROM drafts",
    "DELETE FROM exports",
    "DELETE FROM interviews",
    "DELETE FROM review_items",
    "DELETE FROM classifications",
    "DELETE FROM extractions",
    "DELETE FROM intake_items",
    "DELETE FROM documents",
    "DELETE FROM batches",
    "DELETE FROM rules WHERE key LIKE 't-%'",
    "UPDATE rules SET created_at = now() - interval '30 days'",
]


def connect() -> psycopg.Connection:
    return psycopg.connect(get_settings().libpq_url, row_factory=namedtuple_row)


def one(sql: str, params: tuple = ()) -> Any:
    with connect() as conn:
        return conn.execute(sql, params).fetchone()


def all_rows(sql: str, params: tuple = ()) -> list:
    with connect() as conn:
        return conn.execute(sql, params).fetchall()


def entity_id(key: str) -> str:
    return one("SELECT id FROM entities WHERE key = %s", (key,)).id


def batch() -> str:
    bid = new_id("bat")
    with connect() as conn:
        conn.execute("INSERT INTO batches (id, source, status) VALUES (%s, 'drop', 'done')", (bid,))
    return bid


def document(
    title: str,
    *,
    entity: str | None = "cabinet",
    category: str | None = "payment_calls",
    counterparty: str | None = None,
    doc_date: date | None = None,
    amount: float | None = None,
    currency: str = "EUR",
    due_date: date | None = None,
    status: str = "filed",
    reasons: tuple[str, ...] = (),
    text: str = "",
    filed_at: datetime | None = None,
    fiscal_year: int | None = None,
    deleted: bool = False,
    batch_id: str | None = None,
) -> str:
    did = new_id("doc")
    sha = hashlib.sha256(did.encode()).hexdigest()
    filed = status == "filed"
    location = "trash" if deleted else ("archive" if filed else "inbox")
    folder = one("SELECT folder_name FROM entities WHERE key = %s", (entity,)) if entity else None
    path = f"{folder.folder_name}/{did}.pdf" if filed and folder else f"{did}.pdf"
    cpt = one("SELECT id, name FROM counterparties WHERE key = %s", (counterparty,))
    head = norm(" ".join(x for x in (title, cpt.name if cpt else "") if x))
    with connect() as conn:
        conn.execute(
            """INSERT INTO documents (id, sha256, original_name, mime_type, size_bytes, source,
                 batch_id, location, current_path, status, pipeline_stage, reasons, title,
                 entity_id, category_id, counterparty_id, doc_date, fiscal_year, amount, currency,
                 due_date, confidence, band, filed_at, filed_by, deleted_at, fts)
               VALUES (%s, %s, %s, 'application/pdf', 1000, 'drop', %s, %s, %s, %s, 'done', %s,
                 %s, (SELECT id FROM entities WHERE key = %s), %s, %s, %s, %s, %s, %s, %s, 92,
                 'high', %s, %s, %s,
                 setweight(to_tsvector('mona', %s), 'A') || setweight(to_tsvector('mona', %s), 'C'))
            """,
            (
                did,
                sha,
                f"{did}.pdf",
                batch_id or batch(),
                location,
                path,
                status,
                list(reasons),
                title,
                entity,
                category,
                cpt.id if cpt else None,
                doc_date,
                fiscal_year or (doc_date.year if doc_date and entity else None),
                amount,
                currency if amount is not None else None,
                due_date,
                (filed_at or datetime.now(UTC)) if filed else None,
                "mona" if filed else None,
                datetime.now(UTC) if deleted else None,
                head,
                norm(text),
            ),
        )
    return did


def deadline(
    label: str,
    due: date,
    *,
    entity: str = "cabinet",
    amount: float | None = None,
    document_id: str | None = None,
    status: str = "open",
) -> str:
    did = new_id("ddl")
    with connect() as conn:
        conn.execute(
            """INSERT INTO deadlines (id, document_id, entity_id, label, due_date, amount,
                 currency, status, origin)
               VALUES (%s, %s, (SELECT id FROM entities WHERE key = %s), %s, %s, %s, %s, %s,
                 'extracted')""",
            (
                did,
                document_id,
                entity,
                label,
                due,
                amount,
                "EUR" if amount is not None else None,
                status,
            ),
        )
    return did


def reminder(remind_on: date, *, deadline_id: str | None = None, document_id: str | None = None):
    rid = new_id("rem")
    with connect() as conn:
        conn.execute(
            "INSERT INTO reminders (id, deadline_id, document_id, remind_on, note, created_by)"
            " VALUES (%s, %s, %s, %s, 'call them', 'user')",
            (rid, deadline_id, document_id, remind_on),
        )
    return rid


def rule(key: str, conditions: list[dict], action: dict, *, created_at: datetime | None = None):
    rid = new_id("rul")
    text = {"en": key, "fr": key, "ro": key}
    with connect() as conn:
        conn.execute(
            """INSERT INTO rules (id, key, name, state, source, priority, conditions, action,
                 condition_text, created_at)
               VALUES (%s, %s, %s, 'active', 'interview', 50, %s, %s, %s, %s)""",
            (
                rid,
                key,
                f"Rule {key}",
                json.dumps(conditions),
                json.dumps(action),
                json.dumps(text),
                created_at or datetime.now(UTC),
            ),
        )
    return rid


def interview(open_questions: int = 2, status: str = "ready") -> str:
    iid = new_id("int")
    with connect() as conn:
        conn.execute(
            "INSERT INTO interviews (id, kind, status, scope, lang) VALUES (%s, 'debrief', %s,"
            " '{}', 'en')",
            (iid, status),
        )
        for n in range(1, open_questions + 1):
            conn.execute(
                """INSERT INTO interview_questions (id, interview_id, ordinal, text, impact,
                     affected_document_ids, evidence, options, suggestion_confidence)
                   VALUES (%s, %s, %s, 'Who holds it?', 1, '{}', '[]', '[]', 60)""",
                (new_id("qst"), iid, n),
            )
    return iid


def conversation(title: str = "t") -> str:
    cid = new_id("cnv")
    with connect() as conn:
        conn.execute("INSERT INTO conversations (id, title) VALUES (%s, %s)", (cid, title))
    return cid


def turn(
    conversation_id: str | None = None,
    *,
    status: str = "open",
    expires_in_s: int = 120,
    user_text: str = "x",
    parts: list | None = None,
    reply_language: str = "en",
) -> tuple[str, str]:
    """Insert a turn (and a conversation unless given); returns (conversation_id, turn_id)."""
    cid = conversation_id or conversation()
    tid = new_id("trn")
    with connect() as conn:
        conn.execute(
            """INSERT INTO chat_turns (id, conversation_id, status, user_text, ui_message_id,
                 reply_language, lease_expires_at, parts, closed_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s,
                 CASE WHEN %s <> 'open' THEN now() END)""",
            (
                tid,
                cid,
                status,
                user_text,
                new_id("msg")[4:],
                reply_language,
                datetime.now(UTC) + timedelta(seconds=expires_in_s),
                json.dumps(parts or []),
                status,
            ),
        )
    return cid, tid


def note(conversation_id: str, text: str, *, kind: str = "rule.apply") -> str:
    nid = new_id("not")
    with connect() as conn:
        conn.execute(
            "INSERT INTO card_action_notes (id, conversation_id, kind, text) VALUES (%s, %s, %s,"
            " %s)",
            (nid, conversation_id, kind, text),
        )
    return nid


def card_rows() -> list:
    return all_rows(
        "SELECT id, tool, kind, subject, channel, turn_id, emitted_at FROM card_events"
        " ORDER BY created_at, id"
    )


def turn_row(turn_id: str) -> Any:
    return one("SELECT * FROM chat_turns WHERE id = %s", (turn_id,))


def notes_of(conversation_id: str) -> list:
    return all_rows(
        "SELECT id, text, consumed_turn_id FROM card_action_notes WHERE conversation_id = %s"
        " ORDER BY created_at, id",
        (conversation_id,),
    )

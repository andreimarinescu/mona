"""S5 spike chat tables (dropped by 0004)

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-30
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ["spike_card_events", "spike_interviews", "spike_chat_turns", "spike_conversations"]

UPGRADE = [
    """CREATE TABLE spike_conversations (
        id text PRIMARY KEY,
        hermes_session_id text NOT NULL UNIQUE,
        title text NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        last_message_at timestamptz NOT NULL DEFAULT now())""",
    """CREATE TABLE spike_chat_turns (
        id text PRIMARY KEY,
        conversation_id text NOT NULL REFERENCES spike_conversations (id) ON DELETE CASCADE,
        status text NOT NULL DEFAULT 'open',
        user_ordinal integer NOT NULL,
        ui_message_id text NOT NULL,
        reply_language text NOT NULL,
        opened_at timestamptz NOT NULL DEFAULT now(),
        lease_expires_at timestamptz NOT NULL,
        closed_at timestamptz,
        reasoning_ms integer,
        finish_reason text,
        error_code text,
        usage jsonb)""",
    "CREATE UNIQUE INDEX spike_chat_turns_one_open ON spike_chat_turns (conversation_id)"
    " WHERE status = 'open'",
    """CREATE TABLE spike_card_events (
        id text PRIMARY KEY,
        tool text NOT NULL,
        kind text NOT NULL,
        subject jsonb NOT NULL,
        channel text NOT NULL DEFAULT 'web',
        turn_id text REFERENCES spike_chat_turns (id) ON DELETE SET NULL,
        emitted_at timestamptz,
        created_at timestamptz NOT NULL DEFAULT now())""",
    "CREATE INDEX spike_card_events_turn ON spike_card_events (turn_id, created_at)",
    """CREATE TABLE spike_interviews (
        id text PRIMARY KEY,
        topic text NOT NULL,
        payload jsonb NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now())""",
]


def upgrade() -> None:
    for stmt in UPGRADE:
        op.execute(stmt)


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table}")

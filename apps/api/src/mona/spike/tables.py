from sqlalchemy import (
    TIMESTAMP,
    Column,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Table,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData()

now = text("now()")

conversations = Table(
    "spike_conversations",
    metadata,
    Column("id", Text, primary_key=True),
    Column("hermes_session_id", Text, nullable=False, unique=True),
    Column("title", Text, nullable=False),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=now),
    Column("last_message_at", TIMESTAMP(timezone=True), nullable=False, server_default=now),
)

chat_turns = Table(
    "spike_chat_turns",
    metadata,
    Column("id", Text, primary_key=True),
    Column(
        "conversation_id",
        Text,
        ForeignKey("spike_conversations.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("status", Text, nullable=False, server_default="open"),
    Column("user_ordinal", Integer, nullable=False),
    Column("ui_message_id", Text, nullable=False),
    Column("reply_language", Text, nullable=False),
    Column("opened_at", TIMESTAMP(timezone=True), nullable=False, server_default=now),
    Column("lease_expires_at", TIMESTAMP(timezone=True), nullable=False),
    Column("closed_at", TIMESTAMP(timezone=True)),
    Column("reasoning_ms", Integer),
    Column("finish_reason", Text),
    Column("error_code", Text),
    Column("usage", JSONB),
    Index(
        "spike_chat_turns_one_open",
        "conversation_id",
        unique=True,
        postgresql_where=text("status = 'open'"),
    ),
)

card_events = Table(
    "spike_card_events",
    metadata,
    Column("id", Text, primary_key=True),
    Column("tool", Text, nullable=False),
    Column("kind", Text, nullable=False),
    Column("subject", JSONB, nullable=False),
    Column("channel", Text, nullable=False, server_default="web"),
    Column("turn_id", Text, ForeignKey("spike_chat_turns.id", ondelete="SET NULL")),
    Column("emitted_at", TIMESTAMP(timezone=True)),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=now),
    Index("spike_card_events_turn", "turn_id", "created_at"),
)

interviews = Table(
    "spike_interviews",
    metadata,
    Column("id", Text, primary_key=True),
    Column("topic", Text, nullable=False),
    Column("payload", JSONB, nullable=False),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=now),
)

"""Browser sessions (C2 §2.2) and the early-debrief setting (amendment A9)

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-01
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE auth_sessions (
          id text PRIMARY KEY CHECK (id ~ '^ses_[0-9a-hjkmnp-tv-z]{26}$'),
          token_hash text NOT NULL UNIQUE CHECK (token_hash ~ '^[0-9a-f]{64}$'),
          created_at timestamptz NOT NULL DEFAULT now(),
          expires_at timestamptz NOT NULL,
          last_active_at timestamptz NOT NULL DEFAULT now(),
          revoked_at timestamptz NULL,
          user_agent text NULL CHECK (length(user_agent) <= 300),
          updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX auth_sessions_live ON auth_sessions (expires_at) WHERE revoked_at IS NULL"
    )
    op.execute(
        "ALTER TABLE settings ADD COLUMN debrief_early_min smallint NOT NULL DEFAULT 5"
        " CHECK (debrief_early_min BETWEEN 1 AND 50)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE settings DROP COLUMN debrief_early_min")
    op.execute("DROP TABLE auth_sessions")

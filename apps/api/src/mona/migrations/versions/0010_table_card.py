"""Inline table cards: `exports.format = 'table'`, `exports.spec`, card kind `table` (A36)

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-09
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KINDS = "'doc','deadline','interview','rulePreview','draft','export'"


def upgrade() -> None:
    op.execute(
        "ALTER TABLE exports DROP CONSTRAINT exports_format_check,"
        " ADD CONSTRAINT exports_format_check"
        " CHECK (format IN ('csv','xlsx','docx','table')),"
        " ADD COLUMN spec jsonb NULL"
    )
    op.execute(
        "ALTER TABLE card_events DROP CONSTRAINT card_events_kind_check,"
        f" ADD CONSTRAINT card_events_kind_check CHECK (kind IN ({KINDS},'table'))"
    )


def downgrade() -> None:
    op.execute("DELETE FROM card_events WHERE kind = 'table'")
    op.execute(
        "ALTER TABLE card_events DROP CONSTRAINT card_events_kind_check,"
        f" ADD CONSTRAINT card_events_kind_check CHECK (kind IN ({KINDS}))"
    )
    op.execute(
        "DELETE FROM file_ops WHERE action = 'export' AND subject_id IN"
        " (SELECT id FROM exports WHERE format = 'table')"
    )
    op.execute("DELETE FROM exports WHERE format = 'table'")
    op.execute(
        "ALTER TABLE exports DROP COLUMN spec, DROP CONSTRAINT exports_format_check,"
        " ADD CONSTRAINT exports_format_check CHECK (format IN ('csv','xlsx','docx'))"
    )

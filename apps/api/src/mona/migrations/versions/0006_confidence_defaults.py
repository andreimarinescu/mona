"""Confidence thresholds default to 90/75 (amendment A18)

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-01
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE settings ALTER COLUMN confidence_high SET DEFAULT 90,"
        " ALTER COLUMN confidence_low SET DEFAULT 75"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE settings ALTER COLUMN confidence_high SET DEFAULT 85,"
        " ALTER COLUMN confidence_low SET DEFAULT 60"
    )

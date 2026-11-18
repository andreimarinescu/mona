"""The journal's `deadline.status` action (amendment A60)

Revision ID: 0011_deadline_status
Revises: 0010
Create Date: 2026-11-18
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0011_deadline_status"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACTIONS = (
    "'file','move','rename','unfile','delete','undo','redo',"
    "'doc.update','rule.create','rule.change','deadline.add','reminder.add','mark.unreadable',"
    "'export'"
)


def upgrade() -> None:
    op.execute(
        "ALTER TABLE file_ops DROP CONSTRAINT file_ops_action_check,"
        f" ADD CONSTRAINT file_ops_action_check CHECK (action IN ({ACTIONS},'deadline.status'))"
    )


def downgrade() -> None:
    op.execute("DELETE FROM file_ops WHERE action = 'deadline.status'")
    op.execute(
        "ALTER TABLE file_ops DROP CONSTRAINT file_ops_action_check,"
        f" ADD CONSTRAINT file_ops_action_check CHECK (action IN ({ACTIONS}))"
    )

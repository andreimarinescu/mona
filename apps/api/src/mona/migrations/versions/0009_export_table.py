"""Table exports (CSV, XLSX, DOCX) and their activity entry (amendment A31)

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-01
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACTIONS = (
    "'file','move','rename','unfile','delete','undo','redo',"
    "'doc.update','rule.create','rule.change','deadline.add','reminder.add','mark.unreadable'"
)


def upgrade() -> None:
    op.execute(
        "ALTER TABLE exports ALTER COLUMN entity_id DROP NOT NULL,"
        " ALTER COLUMN fiscal_year DROP NOT NULL,"
        " ADD COLUMN format text NULL CHECK (format IN ('csv','xlsx','docx')),"
        " ADD COLUMN title text NULL,"
        " ADD COLUMN file_path text NULL,"
        " ADD COLUMN truncated boolean NOT NULL DEFAULT false,"
        " ADD CONSTRAINT exports_pack_scope_check"
        " CHECK (format IS NOT NULL OR (entity_id IS NOT NULL AND fiscal_year IS NOT NULL))"
    )
    op.execute(
        "ALTER TABLE file_ops DROP CONSTRAINT file_ops_action_check,"
        f" ADD CONSTRAINT file_ops_action_check CHECK (action IN ({ACTIONS},'export'))"
    )


def downgrade() -> None:
    op.execute("DELETE FROM file_ops WHERE action = 'export'")
    op.execute(
        "ALTER TABLE file_ops DROP CONSTRAINT file_ops_action_check,"
        f" ADD CONSTRAINT file_ops_action_check CHECK (action IN ({ACTIONS}))"
    )
    op.execute("DELETE FROM exports WHERE format IS NOT NULL")
    op.execute(
        "ALTER TABLE exports DROP CONSTRAINT exports_pack_scope_check,"
        " DROP COLUMN truncated, DROP COLUMN file_path, DROP COLUMN title, DROP COLUMN format,"
        " ALTER COLUMN fiscal_year SET NOT NULL, ALTER COLUMN entity_id SET NOT NULL"
    )

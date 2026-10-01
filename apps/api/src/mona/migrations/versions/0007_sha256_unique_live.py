"""documents.sha256 is unique among live documents (amendment A24)

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-01
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE documents DROP CONSTRAINT documents_sha256_key")
    op.execute(
        "CREATE UNIQUE INDEX documents_sha256_live ON documents (sha256) WHERE deleted_at IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX documents_sha256_live")
    op.execute("ALTER TABLE documents ADD CONSTRAINT documents_sha256_key UNIQUE (sha256)")

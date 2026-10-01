"""documents.payment_iban and its evidence row (amendment A30)

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-01
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KEYS = (
    "'entity','counterparty','issuer','reference','doc_type','doc_date',"
    "'period_start','period_end','amount','due_date','addressee'"
)


def upgrade() -> None:
    op.execute(
        "ALTER TABLE documents ADD COLUMN payment_iban text NULL"
        " CHECK (payment_iban ~ '^[A-Z]{2}[0-9]{2}[0-9A-Z]{11,30}$')"
    )
    op.execute(
        "ALTER TABLE extraction_fields DROP CONSTRAINT extraction_fields_key_check,"
        f" ADD CONSTRAINT extraction_fields_key_check CHECK (key IN ({KEYS},'payment_iban'))"
    )


def downgrade() -> None:
    op.execute("DELETE FROM extraction_fields WHERE key = 'payment_iban'")
    op.execute(
        "ALTER TABLE extraction_fields DROP CONSTRAINT extraction_fields_key_check,"
        f" ADD CONSTRAINT extraction_fields_key_check CHECK (key IN ({KEYS}))"
    )
    op.execute("ALTER TABLE documents DROP COLUMN payment_iban")

"""Add account_id to documents table for multi-tenancy.

Revision ID: 0003
Revises: 0002

NOTE: The server_default='dev' backfill is intentional for dev environments only.
Production deployments start with an empty table, so no real data is affected.
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add column with server_default to backfill any existing dev rows
    op.add_column(
        "documents",
        sa.Column("account_id", sa.Text(), nullable=False, server_default="dev"),
    )
    # Remove server_default — new rows must supply account_id explicitly
    op.alter_column("documents", "account_id", server_default=None)
    op.create_index("ix_documents_account_id", "documents", ["account_id"])


def downgrade() -> None:
    op.drop_index("ix_documents_account_id", table_name="documents")
    op.drop_column("documents", "account_id")

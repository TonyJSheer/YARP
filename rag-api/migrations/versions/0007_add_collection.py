"""Add collection column to documents table.

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("collection", sa.Text(), nullable=False, server_default="default"),
    )
    op.alter_column("documents", "collection", server_default=None)
    op.create_index("ix_documents_collection", "documents", ["account_id", "collection"])


def downgrade() -> None:
    op.drop_index("ix_documents_collection", table_name="documents")
    op.drop_column("documents", "collection")

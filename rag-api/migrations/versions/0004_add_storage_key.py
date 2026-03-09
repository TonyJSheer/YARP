"""Add storage_key column to documents table.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("storage_key", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("documents", "storage_key")

"""Add error_message column to documents table.

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("error_message", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("documents", "error_message")

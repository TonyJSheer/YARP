"""Add metadata JSONB column to documents table.

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("doc_metadata", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("documents", "doc_metadata")

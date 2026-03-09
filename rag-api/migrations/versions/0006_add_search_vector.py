"""Add search_vector tsvector column and GIN index to chunks table.

Revision ID: 0006
Revises: 0005
"""

from alembic import op

revision: str = "0006"
down_revision: str = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE chunks
        ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (to_tsvector('english', text)) STORED
    """)
    op.execute("CREATE INDEX ix_chunks_search_vector ON chunks USING GIN (search_vector)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chunks_search_vector")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS search_vector")

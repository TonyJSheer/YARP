"""Resize embedding column from vector(1536) to vector(768)."""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Resets existing embeddings to NULL (dimension mismatch — must re-embed)
    op.execute("ALTER TABLE chunks ALTER COLUMN embedding TYPE vector(768) USING NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE chunks ALTER COLUMN embedding TYPE vector(1536) USING NULL")

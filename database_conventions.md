# Database Conventions

---

## Migrations (Alembic)

All schema changes require a migration. No exceptions, including development.

```bash
# From services/api/

# Generate a new migration (inspect model changes automatically)
uv run alembic revision --autogenerate -m "add_tasks_table"

# Apply all pending migrations
uv run alembic upgrade head

# Roll back one step
uv run alembic downgrade -1

# Check current applied revision
uv run alembic current

# Show migration history
uv run alembic history
```

Rules:
- Never edit an existing migration file — create a new one
- Migration description must be specific: `add_tasks_table`, `add_assigned_user_to_tasks`, `add_index_tasks_status` — not `update` or `changes`
- Every migration must implement `downgrade()` — make it reversible
- Run `alembic upgrade head` in CI before running tests

---

## Table Naming

- Lowercase `snake_case`, plural: `tasks`, `user_accounts`, `project_members`
- Junction/association tables: `task_assignees`, `user_roles`
- No table prefixes, no Hungarian notation

---

## Column Conventions

| Pattern | Convention | Example |
|---|---|---|
| Primary key | `id` UUID | `id UUID PRIMARY KEY DEFAULT gen_random_uuid()` |
| Foreign key | `{singular_table}_id` | `user_id UUID REFERENCES users(id)` |
| Timestamps | `created_at`, `updated_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` |
| Soft deletes | `deleted_at` nullable | `deleted_at TIMESTAMPTZ` |
| Status fields | `status` text with check constraint | `status TEXT NOT NULL DEFAULT 'pending'` |
| Booleans | `is_` or `has_` prefix | `is_active`, `has_been_sent` |

Always include `created_at` on every table. Include `updated_at` on tables that are updated after creation. Use `deleted_at` for soft deletes on user-facing data.

---

## Soft Deletes

Prefer soft deletes over hard deletes for user-facing data. All queries on soft-deletable tables must filter `WHERE deleted_at IS NULL` unless intentionally querying deleted records.

---

## Indexes

Add indexes for:
- All foreign key columns (Postgres does not auto-index these)
- Columns used in frequent `WHERE` clauses
- Composite indexes for common multi-column filter patterns

```sql
CREATE INDEX ix_tasks_user_id ON tasks(user_id);
CREATE INDEX ix_tasks_status_created_at ON tasks(status, created_at DESC);
```

---

## SQLAlchemy Model Pattern

```python
import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from app.db import Base


class Task(Base):
    __tablename__ = "tasks"

    id: uuid.UUID = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: str = Column(String, nullable=False)
    status: str = Column(String, nullable=False, default="pending")
    user_id: uuid.UUID = Column(UUID(as_uuid=True), nullable=False, index=True)
    created_at: datetime = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: datetime = Column(DateTime(timezone=True), onupdate=func.now())
    deleted_at: datetime | None = Column(DateTime(timezone=True), nullable=True)
```

---

## Seed Data

Seed scripts live in `scripts/seed.py`. Running `make dev` should optionally seed the database for local development. Seed scripts must be idempotent — safe to run multiple times.

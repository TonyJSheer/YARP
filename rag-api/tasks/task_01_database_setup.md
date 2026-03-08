# Task 01 — Database Setup

**Type**: `infrastructure`

**Summary**: Enable the pgvector extension and create the `documents` and `chunks` tables via an Alembic migration. This is the foundation for all subsequent tasks.

---

## Context

**Background**: The scaffold has SQLAlchemy models defined in `app/models/` but no migration has been created yet. This task creates the initial migration and verifies the database initialises correctly.

**Affected components**:
- [x] Database schema
- [x] Backend API (migrations/env.py already configured)

---

## Requirements

**Functional**:
- `pgvector` extension enabled in PostgreSQL
- `documents` table created with all columns from the model
- `chunks` table created with all columns including `embedding vector(1536)`
- Foreign key from `chunks.document_id` → `documents.id` with `ON DELETE CASCADE`
- `make migrate` runs without error against a fresh database

**Non-functional**:
- Migration must implement `downgrade()` (drop tables, drop extension)

---

## Implementation Guidelines

**Files to create**:
- `migrations/versions/0001_initial.py` — Alembic migration

**Architecture constraints**:
- Use `op.execute("CREATE EXTENSION IF NOT EXISTS vector")` to enable pgvector
- Do not hand-write SQL for the tables — use `op.create_table()` with SQLAlchemy column types
- `chunks.embedding` column type: `Vector(1536)` from `pgvector.sqlalchemy`

**Steps**:
1. Run `uv run alembic revision --autogenerate -m "initial"` to generate the migration
2. Review the generated file — confirm pgvector extension creation is included
3. Add `op.execute("CREATE EXTENSION IF NOT EXISTS vector")` at the top of `upgrade()` if not auto-generated
4. Add `op.execute("DROP EXTENSION IF EXISTS vector")` at the bottom of `downgrade()`
5. Run `uv run alembic upgrade head` to apply

---

## API Changes

None.

---

## Test Requirements

- Verify `make migrate` runs cleanly on a fresh `docker compose up postgres -d`
- Verify both tables exist: `\dt` in psql should show `documents` and `chunks`
- Verify `chunks.embedding` is a vector column: `\d chunks` should show `vector(1536)`

---

## Acceptance Criteria

- [ ] `uv run alembic upgrade head` runs without error on a fresh database
- [ ] `documents` and `chunks` tables exist with correct columns
- [ ] `pgvector` extension is enabled
- [ ] `uv run alembic downgrade base` runs without error
- [ ] `make test` still passes (health test should not be affected)

---

## Validation Steps

```bash
docker compose up postgres -d
make migrate
# Verify in psql:
docker compose exec postgres psql -U rag -d rag -c "\dt"
docker compose exec postgres psql -U rag -d rag -c "\d chunks"
make test
```

---

## Risks

- Alembic autogenerate may not include the pgvector extension creation — must be added manually
- `Vector` column type import in the migration file: `from pgvector.sqlalchemy import Vector`

# Task P2-01 — Multi-Tenancy Schema Migration

**Type**: `infrastructure`

**Summary**: Add `account_id` to the `documents` table and update all service-layer queries to filter by it. This is the foundation for all Phase 2 work — no tenant isolation exists without this.

---

## Context

**Background**: Phase 1 is single-tenant; the DB has no concept of ownership. Phase 2 makes the system multi-tenant by scoping every document (and transitively every chunk) to an `account_id`. This task adds the column, creates the migration, and updates all DB queries to include the `account_id` filter. Auth (how you get the `account_id`) is Task P2-02.

**Affected components**:
- [x] Database schema
- [x] ORM models
- [x] Service layer (ingestion, retrieval)
- [x] Routers (pass `account_id` through; hard-code a dev sentinel for now)

---

## Requirements

**Functional**:
- `documents.account_id TEXT NOT NULL` — every document is owned by an account
- Index on `documents(account_id)` for fast per-tenant queries
- `ingestion.ingest_document()` accepts and stores `account_id`
- `retrieval.retrieve_chunks()` filters by `account_id` so cross-tenant data is never returned
- A placeholder `account_id = "dev"` is used in the REST API routers until P2-02 wires up real auth — this is intentional and clearly commented

**Non-functional**:
- Migration must implement `downgrade()` (drop index, drop column)
- No existing data is broken — migration sets `account_id = 'dev'` for any rows present (dev environment only; prod starts fresh)

---

## Implementation Guidelines

**Files to create**:
- `migrations/versions/0002_add_account_id.py` — Alembic migration

**Files to modify**:
- `app/models/document.py` — add `account_id: str` column
- `app/services/ingestion.py` — accept `account_id` in `ingest_document()`
- `app/services/retrieval.py` — filter `chunks` join by `documents.account_id`
- `app/routers/documents.py` — pass `account_id="dev"` placeholder (TODO comment)
- `app/routers/query.py` — pass `account_id="dev"` placeholder (TODO comment)

**Architecture constraints**:
- Chunks do NOT get an `account_id` column — they inherit scope via `document_id` FK
- All chunk retrieval must JOIN through `documents` to filter by `account_id`; never skip this join
- The `"dev"` placeholder must have a clearly marked `# TODO(P2-02): replace with auth dependency` comment

**Migration sketch**:

```python
# migrations/versions/0002_add_account_id.py

def upgrade() -> None:
    op.add_column("documents", sa.Column("account_id", sa.Text(), nullable=False, server_default="dev"))
    op.alter_column("documents", "account_id", server_default=None)  # remove server default after backfill
    op.create_index("ix_documents_account_id", "documents", ["account_id"])

def downgrade() -> None:
    op.drop_index("ix_documents_account_id", table_name="documents")
    op.drop_column("documents", "account_id")
```

**Model change**:

```python
# app/models/document.py
account_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
```

**Retrieval change** (critical — must filter account_id):

```python
# app/services/retrieval.py
def retrieve_chunks(query: str, account_id: str, top_k: int, db: Session) -> list[Chunk]:
    # embed query ...
    # query must JOIN documents and filter WHERE documents.account_id = account_id
    results = (
        db.query(Chunk)
        .join(Document, Chunk.document_id == Document.id)
        .filter(Document.account_id == account_id)
        .order_by(Chunk.embedding.cosine_distance(query_embedding))
        .limit(top_k)
        .all()
    )
    return results
```

---

## API Changes

None visible externally in this task. The `account_id` is plumbed internally with a dev placeholder.

---

## Test Requirements

Add to existing test files where relevant:

- `test_retrieval.py` — verify that chunks belonging to a different `account_id` are NOT returned for a query. Create two documents with different `account_id` values; query as one account; assert only that account's chunks appear.
- `test_documents.py` — verify upload stores the `account_id` on the document record.

---

## Acceptance Criteria

- [ ] `uv run alembic upgrade head` runs without error
- [ ] `documents` table has `account_id TEXT NOT NULL` column with index
- [ ] `retrieval.retrieve_chunks()` signature includes `account_id` parameter
- [ ] `ingestion.ingest_document()` signature includes `account_id` parameter
- [ ] Retrieval NEVER returns chunks whose parent document has a different `account_id`
- [ ] Routers pass `account_id="dev"` with a `# TODO(P2-02)` comment
- [ ] `make test` passes
- [ ] `make lint && make typecheck` passes

---

## Validation Steps

```bash
make migrate
# Verify column exists
docker compose exec postgres psql -U rag -d rag -c "\d documents"
# Should show account_id column and ix_documents_account_id index

# Manual isolation test
curl -X POST http://localhost:8000/documents -F "file=@test.txt"
# Check DB: account_id should be "dev"
docker compose exec postgres psql -U rag -d rag -c "SELECT id, account_id, filename FROM documents;"

make test
make lint
make typecheck
```

---

## Risks

- `server_default="dev"` in the migration is only safe because this is a dev environment. Document this constraint clearly in the migration comment.
- The retrieval JOIN adds a small perf cost — negligible at Phase 2 scale, but note it.
- If any service test creates documents without `account_id`, those tests will fail — update them to pass `account_id="dev"` or `"test"`.

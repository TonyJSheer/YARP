# Running the Test Suite

## Prerequisites

1. **Postgres running with pgvector** — the retrieval tests are integration tests that require a live database:
   ```bash
   docker compose up postgres -d
   ```

2. **Migrations applied**:
   ```bash
   make migrate
   ```

3. **Dependencies installed**:
   ```bash
   make setup
   ```

No `.env` file is needed — `tests/conftest.py` sets all required environment variables (`DATABASE_URL`, `ANTHROPIC_API_KEY`, etc.) before any app code is imported.

## Running Tests

```bash
# Full suite
make test

# Verbose output
uv run pytest -v

# Single file
uv run pytest tests/test_retrieval.py -v

# Short traceback on failure
uv run pytest --tb=short
```

## No Real API Calls

All Anthropic and embedding calls are mocked. The suite passes with `ANTHROPIC_API_KEY=test-key` (the default set in `conftest.py`). You can verify:

```bash
ANTHROPIC_API_KEY=definitely-not-real make test
```

## Test File Overview

| File | Type | What it covers |
|---|---|---|
| `test_health.py` | unit | `GET /health` |
| `test_documents.py` | integration | `POST /documents` upload pipeline |
| `test_chunking.py` | unit | `extract_text()`, `chunk_text()` |
| `test_embedding.py` | unit | `embed_chunks()`, `embed_query()` |
| `test_retrieval.py` | integration | pgvector cosine similarity search |
| `test_generation.py` | unit | prompt construction, `generate_answer()` |
| `test_query.py` | integration | `POST /query`, `POST /query/stream` (SSE) |

## Database State

Integration tests (`test_documents.py`, `test_retrieval.py`) insert rows into the `rag` database. Retrieval fixtures clean up after themselves. Document rows persist (acceptable for Phase 1 dev use).

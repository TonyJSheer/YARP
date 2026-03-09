# Project Blueprint — RAG API

Generated from `project_spec.md` + `ai_blueprint_meta.md`.

This document is the concrete, resolved architecture for the RAG API project. Coding agents work from this document and `docs/AGENTS.md` — they do not need to re-read the spec or meta files.

---

## 1. Product Architecture Overview

A single-service backend API that implements a complete RAG (Retrieval-Augmented Generation) pipeline:

```
Client → FastAPI (POST /documents)
           → text extraction → chunking → embedding (OpenAI) → store in pgvector

Client → FastAPI (POST /query)
           → embed query (OpenAI) → vector search (pgvector) → LLM generation (OpenAI) → return answer + citations

Client → FastAPI (POST /query/stream)
           → same as above, but stream LLM tokens via SSE
```

No frontend, no worker service, no Redis, no cloud infra in Phase 1. Just the API + PostgreSQL + Docker Compose.

---

## 2. Resolved Technology Stack

| Slot | Decision | Justification |
|---|---|---|
| `api_style` | `rest` | Standard HTTP endpoints; no complex querying patterns |
| `auth_method` | `none` | Dev/research tool, Phase 1 only |
| `mobile_support` | `none` | API-only service |
| `redis_hosting` | N/A | No Redis in Phase 1 |
| `realtime` | `sse` | Token streaming on /query/stream only |
| `multitenancy` | `no` | Single-tenant, single-user context |
| `background_jobs` | `none` | Inline ingestion acceptable at this scale |
| `file_storage` | `local` | ./data/uploads; S3 in Phase 2 |
| `deployment_target` | `docker_compose` | Local dev only in Phase 1 |
| `database_migrations` | `alembic` | Standard; enables clean schema evolution |
| `admin_interface` | `none` | Not needed at this scale |
| `external_api_access` | `none` | No inbound partner API |

**Full technology stack:**

| Layer | Technology |
|---|---|
| Backend | Python 3.12 + FastAPI + msgspec |
| Database | PostgreSQL 16 + pgvector extension |
| Embeddings | OpenAI API (text-embedding-ada-002 or configured model) |
| LLM | OpenAI API (gpt-4o or configured model) |
| Package manager | `uv` |
| Tests | pytest |
| Lint / format | ruff |
| Type check | mypy --strict |
| Local infra | Docker Compose |
| Migrations | Alembic |

---

## 3. Infrastructure Layout

Phase 1: Docker Compose only.

```
docker-compose.yml
  api        — FastAPI on port 8000
  postgres   — PostgreSQL 16 + pgvector on port 5432
```

No Redis, no worker container, no cloud infra. Everything runs locally.

Phase 2 additions: Redis container, worker container, S3-compatible storage (or real S3).

---

## 4. Data Architecture

### PostgreSQL

Core tables:

**documents**
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| filename | text | original filename |
| content_type | text | MIME type |
| sha256 | text | dedup / integrity |
| status | text | uploaded / processing / ready / failed |
| created_at | timestamptz | |

**chunks**
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| document_id | UUID FK | → documents.id |
| chunk_index | integer | position within document |
| page_number | integer nullable | from PDF metadata |
| text | text | chunk content |
| embedding | vector(1536) | pgvector column |
| metadata | jsonb | arbitrary chunk metadata |

Alembic migration path:
1. `0001_initial` — enable pgvector extension, create documents + chunks tables

### File Storage

Local: `./data/uploads/` (mounted into the API container).

Phase 2: replace with S3 calls in `services/storage_service.py`.

---

## 5. API Architecture

Style: REST

Base path: `/api/v1/` (or flat `/` for Phase 1 simplicity — TBD at implementation)

| Method | Path | Description |
|---|---|---|
| GET | /health | Health check |
| POST | /documents | Upload a document |
| POST | /query | RAG query (full response) |
| POST | /query/stream | RAG query (SSE streaming) |

No versioning prefix required for Phase 1 given the single consumer (internal / dev use).

**Error format** (from api_conventions.md):
```json
{
  "error": {
    "code": "not_found",
    "message": "Document not found",
    "field": null
  }
}
```

**Streaming**: POST /query/stream returns `Content-Type: text/event-stream`. Each SSE event contains a token chunk. A final `[DONE]` event signals completion.

---

## 6. Frontend Architecture

None in Phase 1. Consumers are curl, test scripts, or downstream services.

---

## 7. Mobile Strategy

Not applicable.

---

## 8. Background Job System

None in Phase 1. Ingestion (chunking + embedding) runs inline on the POST /documents request.

Acceptable because:
- Single-user workload
- Typical document size is small
- Simplicity > latency at this stage

Phase 2 design: Redis list queue, Python worker service, job types: `ingest_document`.

---

## 9. Repository Structure

```
rag-api/
  app/
    main.py             # FastAPI app init, middleware, router registration
    config.py           # Settings from environment via pydantic-settings
    db.py               # SQLAlchemy engine + session factory
    dependencies.py     # Shared FastAPI dependencies (db session)
    routers/
      health.py         # GET /health
      documents.py      # POST /documents
      query.py          # POST /query, POST /query/stream
    models/
      document.py       # SQLAlchemy ORM: documents table
      chunk.py          # SQLAlchemy ORM: chunks table
    schemas/
      document.py       # msgspec Struct: upload request/response
      query.py          # msgspec Struct: query request/response
    services/
      ingestion.py      # Orchestrates extract → chunk → embed → store
      chunking.py       # Text splitting logic
      embedding.py      # OpenAI embeddings API calls
      retrieval.py      # pgvector similarity search
      generation.py     # LLM prompt building + completion
    providers/
      openai_client.py  # OpenAI SDK wrapper
  migrations/
    env.py
    versions/
      0001_initial.py
  tests/
    conftest.py
    test_health.py
    test_chunking.py
    test_retrieval.py
    test_query.py
  data/
    uploads/            # Local file storage (gitignored)
  Dockerfile
  docker-compose.yml
  pyproject.toml        # uv-managed dependencies
  .env.example
  README.md
  Makefile
  docs/
    AGENTS.md
    ARCHITECTURE.md
    DEVELOPMENT.md
```

---

## 10. Development Workflow

```bash
make setup      # uv sync (install all dependencies)
make dev        # docker compose up (api + postgres)
make test       # uv run pytest
make lint       # uv run ruff check . && uv run ruff format --check .
make typecheck  # uv run mypy app
make migrate    # uv run alembic upgrade head
```

Local dev without Docker:
```bash
# Start postgres only
docker compose up postgres -d

# Run API directly
uv run uvicorn app.main:app --reload
```

---

## 11. CI/CD Pipeline

Phase 1: single GitHub Actions workflow.

| File | Trigger | Steps |
|---|---|---|
| `ci.yml` | All PRs + push to main | lint → typecheck → test (with postgres service container) |

No deployment pipeline in Phase 1 (local Docker Compose only).

---

## 12. Testing Strategy

pytest, pragmatic coverage of critical paths.

| Test | What it covers |
|---|---|
| test_health.py | GET /health returns 200 + {"status": "ok"} |
| test_chunking.py | chunk size, overlap, sentence boundary behaviour |
| test_retrieval.py | top-K chunks returned for a known query |
| test_query.py | POST /query returns answer + citations |

Tests use an in-memory SQLite + patched OpenAI calls (no real API calls in CI).

---

## 13. Security Model

Phase 1: no authentication. API is open.

Secrets via environment variables only:
- `OPENAI_API_KEY`
- `DATABASE_URL`
- `OPENAI_EMBED_MODEL`
- `OPENAI_CHAT_MODEL`

Never commit secrets. `.env` is gitignored. `.env.example` has placeholder values.

Phase 2: add API key middleware (`X-API-Key` header).

---

## 14. Observability

- Structured JSON logging via Python `logging` + custom formatter
- Log fields: `level`, `timestamp`, `service`, `request_id`, `message`
- Log ingestion pipeline steps at INFO level (chunk count, embedding batch size, etc.)
- Log errors with full traceback at ERROR level

No distributed tracing in Phase 1.

---

## 15. Deployment Model

Phase 1: Docker Compose only, local machine.

```bash
docker compose up          # Start everything
docker compose down -v     # Tear down including volumes
```

Phase 2+: containerised deployment to a simple platform (Fly.io, Railway, or ECS Fargate). CDK stacks added at that point.

---

## 16. Delivery Roadmap

### Phase 1 — Complete RAG Backend (all 10 build steps)

- [x] Step 1: Base FastAPI project + Docker Compose + Postgres
- [x] Step 2: Database schema (documents + chunks + pgvector)
- [x] Step 3: POST /documents upload endpoint
- [x] Step 4: Text extraction + chunking service
- [x] Step 5: Embedding generation service (OpenAI)
- [x] Step 6: Vector retrieval service (pgvector)
- [x] Step 7: LLM answer generation service
- [x] Step 8: POST /query endpoint
- [x] Step 9: POST /query/stream SSE endpoint
- [x] Step 10: Test suite

### Phase 2 — MCP Server + Multi-Tenancy

> **Goal change**: Phase 2 pivots from "production hardening" to delivering the RAG pipeline as an MCP server. Redis workers and cloud deployment are deferred to Phase 3.

- [ ] P2-01: Multi-tenancy schema (add `account_id` to documents, migration, scoped queries)
- [ ] P2-02: JWT auth service (Bearer token → account_id; MCP_AUTH_TOKEN env var fallback)
- [ ] P2-03: Storage service refactor (account-scoped paths; S3 backend support)
- [ ] P2-04: Document management endpoints (GET /documents, DELETE /documents/{id})
- [ ] P2-05: MCP server (stdio + HTTP transports; tools: upload, query, list, delete)
- [ ] P2-06: Phase 2 test suite (integration tests, CI updates)

See `rag-api/docs/PHASE2_PLAN.md` for full architecture and rationale.
Task specs: `rag-api/tasks/task_p2_01_*.md` through `task_p2_06_*.md`

### Phase 3 — Async + Search Quality + Deployment

- Async ingestion worker (Redis + worker service) — for large files
- Cloud deployment (Fly.io or ECS Fargate)
- Hybrid search (BM25 + vector)
- Reranking (Cohere or local model)
- Metadata filtering
- OAuth2 / token issuance service

---

## Blueprint Validation Checklist

- [x] All decision slots resolved with justification documented
- [x] Technology stack confirmed
- [x] Infrastructure layout defined
- [x] Repository structure defined
- [x] Deployment model defined
- [x] Testing approach defined
- [x] Phase 1 scope clearly bounded
- [x] Open questions documented (section 16 + project_spec.md)

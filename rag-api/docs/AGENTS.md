# AGENTS.md

**This file is the operating contract between this repository and AI coding agents.**

Read this file at the start of every session before touching any code.

---

## Project

**Name**: rag-api

**Description**: A backend RAG (Retrieval-Augmented Generation) API service. Accepts document uploads, extracts and chunks text, generates embeddings via OpenAI, stores vectors in PostgreSQL with pgvector, and answers questions by retrieving relevant chunks and generating a grounded response with citations. Supports streaming via SSE.

**Stack**: Python 3.12 + FastAPI + msgspec | PostgreSQL 16 + pgvector | OpenAI API | Docker Compose

---

## Repository Structure

```
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
  versions/
tests/
  conftest.py
  test_health.py
  test_chunking.py
  test_retrieval.py
  test_query.py
data/
  uploads/            # Local file storage (gitignored)
docs/
  AGENTS.md           # This file
  ARCHITECTURE.md
  DEVELOPMENT.md
tasks/                # Task specs for coding agents
```

Key locations:
- `app/routers/` — API endpoints (thin: validate input, call service, return response)
- `app/services/` — all business logic
- `app/models/` — SQLAlchemy ORM models
- `app/schemas/` — msgspec request/response types
- `app/providers/` — external API clients (OpenAI)
- `migrations/versions/` — Alembic migration files
- `tasks/` — task specs for each build step

---

## Architecture Decisions

| Decision | Value | Notes |
|---|---|---|
| API style | rest | Standard HTTP endpoints |
| Auth method | none | Open API — Phase 1 dev context only |
| Background jobs | none | Ingestion runs inline on upload |
| Real-time | sse | Token streaming on POST /query/stream only |
| Multi-tenancy | no | Single-tenant |
| File storage | local | ./data/uploads; S3 in Phase 2 |
| Deployment | docker_compose | Local only in Phase 1 |

---

## Development Commands

All commands from repo root.

```bash
make setup      # uv sync (install all dependencies)
make dev        # docker compose up (starts api + postgres)
make test       # uv run pytest
make lint       # uv run ruff check . && uv run ruff format --check .
make typecheck  # uv run mypy app
make migrate    # uv run alembic upgrade head

# Run a single test file
uv run pytest tests/test_chunking.py

# Run tests matching a name pattern
uv run pytest -k "test_query"

# Run with output (no capture)
uv run pytest -s tests/test_health.py

# Database migrations (PYTHONPATH=. required — use make migrate, not bare alembic)
make migrate
uv run alembic revision --autogenerate -m "description"

# Start postgres only (for running API outside Docker)
docker compose up postgres -d
uv run uvicorn app.main:app --reload
```

---

## Architecture Boundaries

Hard rules — do not cross without explicit instruction:

- **Routers are thin**: validate input, call one service method, return response — no business logic in routers
- **All OpenAI calls go through `providers/openai_client.py`**: never import the openai SDK directly in services
- **All DB access goes through the service layer**: no raw queries in routers
- **Secrets**: environment variables only — never in code or committed files
- **No new packages** without justification in the PR

---

## Coding Standards

**Python**: type annotations required on all functions, `msgspec.Struct` for all API request/response types (not Pydantic), `ruff` for lint/format, `mypy --strict` for types

**Request body parsing**: decode msgspec Structs from `request.body()` in routers — see `app/routers/query.py` for the pattern.

**Naming**: snake_case for files, functions, variables; PascalCase for classes; UPPER_SNAKE for constants

**Services**: each service module has a single responsibility (chunking.py only chunks, embedding.py only embeds)

---

## Database Migrations

- Every schema change requires an Alembic migration
- Never edit existing migrations — create new ones
- Migrations must implement `downgrade()`
- Run `make migrate` before running tests locally

---

## API Conventions

- Error format: `{"error": {"code": "...", "message": "...", "field": null}}`
- No pagination needed in Phase 1
- SSE streaming events: each event is a token string; final event is `[DONE]`

---

## Git Conventions

- Branch: `feat/`, `fix/`, `chore/`, `refactor/`, `docs/`
- Commit: `feat: add chunking service` (imperative, lowercase, no period)
- One concern per PR

---

## Testing Requirements

- Every new endpoint needs at minimum a happy-path test
- Every bugfix needs a test that would have caught it
- OpenAI API calls must be mocked in tests — no real API calls in CI
- Tests must pass before a PR is submitted
- `make test` runs everything

---

## Environment Variables

```
DATABASE_URL=postgresql://rag:rag@localhost:5432/rag
OPENAI_API_KEY=sk-...
OPENAI_EMBED_MODEL=text-embedding-ada-002
OPENAI_CHAT_MODEL=gpt-4o
UPLOAD_DIR=./data/uploads
```

All variables defined in `.env.example`. Copy to `.env` for local dev.

---

## Definition of Done

- [ ] Acceptance criteria from the task spec met
- [ ] `make test` passes
- [ ] `make lint && make typecheck` passes with no new errors
- [ ] Docs updated if architecture, commands, or APIs changed
- [ ] PR submitted with PLAN / CHANGES / TESTS / VALIDATION / RISKS sections

---

## What NOT to Do

- Do not put business logic in routers
- Do not call the OpenAI SDK directly in service files — use `providers/openai_client.py`
- Do not hardcode API keys or model names — use config.py
- Do not modify Alembic migration files after they have been applied
- Do not push directly to `main`
- Do not skip CI with `--no-verify`
- Do not add Redis, workers, or S3 in Phase 1 — those are Phase 2

# Development Guide

## Prerequisites

- Docker + Docker Compose
- Python 3.12
- `uv` — install with `pip install uv` or `brew install uv`

## Local Setup

```bash
# 1. Copy env file and add your OpenAI API key
cp .env.example .env

# 2. Install Python dependencies
make setup

# 3. Start API + Postgres via Docker Compose
make dev

# 4. In a separate terminal, run migrations
make migrate

# 5. Verify
curl http://localhost:8000/health
# {"status": "ok"}
```

## Running the API Without Docker

```bash
# Start Postgres only
docker compose up postgres -d

# Run API with hot reload
uv run uvicorn app.main:app --reload
```

## Running Tests

```bash
# Unit tests (no running services needed for health tests)
make test

# Full test suite with real Postgres (integration tests)
docker compose up postgres -d
make migrate
make test
```

## Common Tasks

### Add a migration

```bash
uv run alembic revision --autogenerate -m "add_column_to_table"
uv run alembic upgrade head
```

### Check lint and types

```bash
make lint
make typecheck
```

### Reset the database

```bash
docker compose down -v   # removes pgdata volume
make dev
make migrate
```

## Environment Variables

See `.env.example` for all variables.

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | yes | — | PostgreSQL connection string |
| `OPENAI_API_KEY` | yes | — | OpenAI API key |
| `OPENAI_EMBED_MODEL` | no | `text-embedding-ada-002` | Embedding model |
| `OPENAI_CHAT_MODEL` | no | `gpt-4o` | Chat completion model |
| `UPLOAD_DIR` | no | `./data/uploads` | Local file upload directory |

## Project Structure

```
app/
  routers/     — thin HTTP handlers (no business logic here)
  services/    — all business logic
  models/      — SQLAlchemy ORM models
  schemas/     — msgspec request/response types
  providers/   — external API clients (OpenAI)
migrations/    — Alembic migration files
tests/         — pytest test suite
```

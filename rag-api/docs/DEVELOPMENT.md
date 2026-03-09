# Development Guide

> **All commands in this guide are run from the `rag-api/` directory**, not the repo root.
> If you cloned YARP, `cd rag-api` first.

## Prerequisites

- Docker + Docker Compose
- Python 3.12
- `uv` — install with `pip install uv` or `brew install uv`

## Local Setup

```bash
# 1. Copy env file and fill in required values
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
# Always use make migrate (sets PYTHONPATH=. for alembic to find app/)
uv run alembic revision --autogenerate -m "add_column_to_table"
make migrate
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
| `ANTHROPIC_API_KEY` | yes | — | Anthropic API key |
| `ANTHROPIC_MODEL` | no | `claude-haiku-4-5-20251001` | Chat model |
| `EMBED_MODEL` | no | `all-mpnet-base-v2` | Embedding model |
| `UPLOAD_DIR` | no | `./data/uploads` | Local file upload directory |
| `JWT_SECRET` | yes | — | Secret for signing JWT bearer tokens |
| `JWT_ALGORITHM` | no | `HS256` | JWT signing algorithm |
| `STORAGE_BACKEND` | no | `local` | `local` or `s3` |
| `S3_BUCKET` | no (s3 only) | — | S3 bucket name |
| `S3_REGION` | no | `us-east-1` | AWS region |
| `AWS_ACCESS_KEY_ID` | no (s3 only) | — | AWS access key |
| `AWS_SECRET_ACCESS_KEY` | no (s3 only) | — | AWS secret key |

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

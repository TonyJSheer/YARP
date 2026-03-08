# rag-api

A RAG (Retrieval-Augmented Generation) backend API. Upload documents, ask questions, get grounded answers with citations.

## Quick Start

```bash
cp .env.example .env
# Add your OPENAI_API_KEY to .env
make setup
make dev
make migrate
```

API: http://localhost:8000
Docs: http://localhost:8000/docs

## Endpoints

| Method | Path | Description |
|---|---|---|
| GET | /health | Health check |
| POST | /documents | Upload a document |
| POST | /query | Ask a question (full response) |
| POST | /query/stream | Ask a question (SSE streaming) |

## Development

See `docs/DEVELOPMENT.md` for full setup, migration, and testing guide.

## Architecture

See `docs/ARCHITECTURE.md` for component map, data model, and service breakdown.

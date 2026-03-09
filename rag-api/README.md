# rag-api

A RAG (Retrieval-Augmented Generation) backend you can connect directly to Claude as an MCP server. Upload your documents, then ask Claude questions — it will query your knowledge base and answer with citations.

- **Embeddings**: local via `sentence-transformers` (no API key, no cost)
- **LLM**: Anthropic Claude (via `ANTHROPIC_API_KEY`)
- **Vector store**: PostgreSQL + pgvector
- **Auth**: per-tenant JWT tokens — each user only sees their own documents
- **Interface**: MCP server (Claude Desktop / Claude Code) + REST API

---

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) (for PostgreSQL)
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- Python 3.12+
- An [Anthropic API key](https://console.anthropic.com/)

---

## Quick Start

```bash
# 1. Clone and install dependencies
git clone <repo-url>
cd rag-api
uv sync

# 2. Configure environment
cp .env.example .env
# Edit .env — set ANTHROPIC_API_KEY and JWT_SECRET (see Environment Variables below)

# 3. Start PostgreSQL
docker compose up postgres -d

# 4. Run migrations
make migrate

# 5. Generate your personal token
uv run python scripts/generate_token.py my-account
# Copy the token — you'll need it in step 6
```

---

## Connecting to Claude

Choose **one** of the two approaches below.

### Option A — stdio (Claude Desktop or Claude Code, local process)

The MCP server runs as a subprocess spawned by the Claude client. No extra port or Docker service needed.

**Claude Code** — add to `.claude/settings.json` in your project, or `~/.claude/settings.json` globally:

```json
{
  "mcpServers": {
    "rag-api": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/rag-api", "run", "rag-mcp"],
      "env": {
        "MCP_AUTH_TOKEN": "<token from step 5>",
        "DATABASE_URL": "postgresql://rag:rag@localhost:5432/rag",
        "ANTHROPIC_API_KEY": "<your-key>",
        "JWT_SECRET": "<same secret as your .env>"
      }
    }
  }
}
```

**Claude Desktop** — add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "rag-api": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/rag-api", "run", "rag-mcp"],
      "env": {
        "MCP_AUTH_TOKEN": "<token from step 5>",
        "DATABASE_URL": "postgresql://rag:rag@localhost:5432/rag",
        "ANTHROPIC_API_KEY": "<your-key>",
        "JWT_SECRET": "<same secret as your .env>"
      }
    }
  }
}
```

Restart Claude Desktop / reload Claude Code after saving the config. You should see the `rag-api` server in the MCP tools list.

---

### Option B — HTTP (remote or Docker Compose)

Run the full stack including the MCP HTTP server:

```bash
docker compose up
```

This starts three services:
- `api` — REST API on `http://localhost:8000`
- `postgres` — PostgreSQL on port 5432
- `mcp` — MCP HTTP server on `http://localhost:8001`

Then configure your MCP client to connect via HTTP:

```json
{
  "mcpServers": {
    "rag-api": {
      "url": "http://localhost:8001/mcp",
      "headers": {
        "Authorization": "Bearer <token from step 5>"
      }
    }
  }
}
```

> **Note**: HTTP MCP transport support varies by client. stdio is recommended for local use.

---

## Available MCP Tools

Once connected, Claude can call these tools on your behalf:

| Tool | Description |
|---|---|
| `upload_document` | Upload a document (base64-encoded). Supported: `.txt`, `.md`, `.pdf` |
| `query_documents` | Ask a question — returns a grounded answer with citations |
| `list_documents` | List all documents in your knowledge base |
| `delete_document` | Delete a document and all its chunks |

Example prompts once connected:
- *"Upload this file to my knowledge base"* (attach a file)
- *"What does my uploaded document say about X?"*
- *"List all my documents"*
- *"Delete the document called report.pdf"*

---

## REST API

The REST API runs on `http://localhost:8000` and mirrors the MCP tools. All endpoints (except `/health`) require `Authorization: Bearer <token>`.

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check — no auth required |
| `POST` | `/documents` | Upload a document (`multipart/form-data`) |
| `GET` | `/documents` | List your documents |
| `DELETE` | `/documents/{id}` | Delete a document |
| `POST` | `/query` | RAG query — returns `{"answer": "...", "citations": [...]}` |
| `POST` | `/query/stream` | RAG query with SSE token streaming |

```bash
TOKEN="<your token>"

# Upload
curl -X POST http://localhost:8000/documents \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/path/to/doc.pdf"

# Query
curl -X POST http://localhost:8000/query \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the main finding?", "top_k": 5}'

# List
curl http://localhost:8000/documents \
  -H "Authorization: Bearer $TOKEN"

# Delete
curl -X DELETE http://localhost:8000/documents/<document_id> \
  -H "Authorization: Bearer $TOKEN"
```

---

## Environment Variables

Copy `.env.example` to `.env` and fill in:

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | yes | — | PostgreSQL connection string |
| `ANTHROPIC_API_KEY` | yes | — | Anthropic API key for LLM generation |
| `JWT_SECRET` | yes | — | Secret for signing/verifying JWT tokens. Use a strong random value. |
| `ANTHROPIC_MODEL` | no | `claude-haiku-4-5-20251001` | Claude model for answer generation |
| `EMBED_MODEL` | no | `all-mpnet-base-v2` | sentence-transformers model for embeddings (runs locally) |
| `UPLOAD_DIR` | no | `./data/uploads` | Local file storage directory |
| `JWT_ALGORITHM` | no | `HS256` | JWT signing algorithm |
| `STORAGE_BACKEND` | no | `local` | `local` or `s3` |
| `S3_BUCKET` | if s3 | — | S3 bucket name |
| `S3_REGION` | if s3 | `us-east-1` | AWS region |
| `AWS_ACCESS_KEY_ID` | if s3 | — | AWS credentials |
| `AWS_SECRET_ACCESS_KEY` | if s3 | — | AWS credentials |

**Generating a strong `JWT_SECRET`:**
```bash
openssl rand -hex 32
```

---

## Token Management

Tokens are JWTs signed with your `JWT_SECRET`. Each token encodes an `account_id` — all documents uploaded with that token are scoped to that account.

```bash
# Generate a token for an account
uv run python scripts/generate_token.py <account_id>

# Example — generate token for "alice"
uv run python scripts/generate_token.py alice
```

Tokens do not expire by default (no `exp` claim). To issue expiring tokens, modify `scripts/generate_token.py` to add an `exp` claim.

**Multiple users**: generate a different token per user. Each user's documents are isolated — user A cannot query user B's documents.

---

## Development

```bash
make setup      # Install all dependencies (uv sync)
make dev        # Start full stack via Docker Compose
make test       # Run test suite
make lint       # ruff check + format check
make typecheck  # mypy --strict
make migrate    # Apply Alembic migrations

# Run API locally (without Docker, requires postgres running)
docker compose up postgres -d
make migrate
uv run uvicorn app.main:app --reload

# Run MCP server locally (stdio mode)
MCP_AUTH_TOKEN=<token> uv run rag-mcp

# Run MCP server locally (HTTP mode)
uv run rag-mcp --transport http --port 8001
```

---

## Architecture

```
MCP Client (Claude Desktop / Claude Code)
    │  stdio or HTTP/SSE
    ▼
MCP Server (app/mcp_server.py)       REST API (app/main.py)
    │                                     │
    └──────────── Service Layer ──────────┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
     PostgreSQL   sentence-    Anthropic
     (pgvector)  transformers   Claude API
                 (local embed)
```

See `docs/ARCHITECTURE.md` for the full component map and data model.

---

## Troubleshooting

**`JWT_SECRET is not set — all authenticated requests will fail`**
→ Add `JWT_SECRET` to your `.env` file.

**`MCP_AUTH_TOKEN not set` in stdio mode**
→ Ensure `MCP_AUTH_TOKEN` is set in the `env` block of your MCP client config (not your shell `.env`).

**`relation "documents" does not exist`**
→ Run `make migrate` to apply database migrations.

**Embeddings are slow on first run**
→ `sentence-transformers` downloads the model (~420MB) on first use. Subsequent runs use the cached model.

**`upload_document` times out for large PDFs**
→ Ingestion (chunking + embedding) is synchronous. Large PDFs may take 30–60 seconds. This is expected in Phase 2 — async workers are a Phase 3 item.

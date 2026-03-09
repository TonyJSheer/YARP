# Task P2-05 — MCP Server

**Type**: `feature`

**Summary**: Implement an MCP (Model Context Protocol) server that exposes the RAG pipeline as tools callable by any MCP-compatible AI client (Claude Desktop, Claude Code, etc.). Supports stdio and HTTP transports. Reuses the existing service layer — no business logic is duplicated.

**Depends on**: P2-01, P2-02, P2-03, P2-04

---

## Context

**Background**: MCP is Anthropic's open standard for connecting AI hosts to tools and data sources. By wrapping the RAG pipeline as an MCP server, any Claude client can call `upload_document`, `query_documents`, `list_documents`, and `delete_document` directly — no HTTP client or curl required from the user.

The MCP server is a **new entry point** alongside the existing FastAPI app. Both entry points share the same service layer. The MCP server is not a replacement for the REST API — it's an additional interface.

**Affected components**:
- [x] New module: `app/mcp_server.py` (or `app/mcp/`)
- [x] `pyproject.toml` (new dependency: `mcp`)
- [x] `docker-compose.yml` (optional: add mcp-server service for HTTP transport)
- [x] Docs (how to configure in Claude Desktop / Claude Code)

---

## Requirements

**Functional**:

The MCP server exposes four tools:

| Tool | Description |
|---|---|
| `upload_document` | Upload a document by providing base64-encoded content and a filename. Returns document_id. |
| `query_documents` | Run a RAG query. Returns answer + citations. |
| `list_documents` | List all documents owned by the caller. |
| `delete_document` | Delete a document by ID. |

All tools are scoped to the authenticated `account_id`:
- **stdio transport**: reads `MCP_AUTH_TOKEN` env var (set in MCP client config)
- **HTTP transport**: reads `Authorization: Bearer <token>` from request headers (MCP HTTP spec)

The server supports both transports, selected by a `--transport` CLI flag.

**Non-functional**:
- MCP server starts in under 2 seconds (no heavy init at startup)
- Tools return structured data (dicts) not raw strings where possible
- Error responses use MCP's error format (not FastAPI's error format)
- The MCP server uses the same DB session factory as the REST API

---

## Implementation Guidelines

**New package to add** (via `uv add`):
- `mcp` — Anthropic's MCP Python SDK (`pip install mcp`)

**Files to create**:
- `app/mcp_server.py` — MCP server entry point
- `app/mcp_tools.py` — tool implementations (thin wrappers calling service layer)

**Files to modify**:
- `pyproject.toml` — add `mcp` dependency, add `[project.scripts]` entry
- `docker-compose.yml` — add optional `mcp` service (HTTP transport)
- `.env.example` — add `MCP_AUTH_TOKEN` documentation comment

**MCP server implementation sketch**:

```python
# app/mcp_server.py
import argparse
import base64
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.server.sse import SseServerTransport

from app.db import SessionLocal
from app.services import auth, ingestion, retrieval, generation, document_service
from app.services.storage import get_storage_service

server = Server("rag-api")

def get_account_id() -> str:
    """For stdio transport: resolve account_id from MCP_AUTH_TOKEN env var."""
    import os
    token = os.getenv("MCP_AUTH_TOKEN", "")
    if not token:
        raise ValueError("MCP_AUTH_TOKEN not set")
    return auth.decode_token(token)


@server.tool()
async def upload_document(filename: str, content_b64: str) -> dict:
    """Upload a document. content_b64 is the base64-encoded file content."""
    account_id = get_account_id()
    data = base64.b64decode(content_b64)
    storage = get_storage_service()
    with SessionLocal() as db:
        doc = await ingestion.ingest_document_from_bytes(
            filename=filename,
            data=data,
            account_id=account_id,
            storage=storage,
            db=db,
        )
    return {"document_id": str(doc.id), "status": doc.status, "chunk_count": doc.chunk_count}


@server.tool()
async def query_documents(question: str, top_k: int = 5) -> dict:
    """Query your documents using RAG. Returns an answer with citations."""
    account_id = get_account_id()
    with SessionLocal() as db:
        chunks = retrieval.retrieve_chunks(question, account_id, top_k, db)
        result = await generation.generate_answer(question, chunks)
    return {"answer": result.answer, "citations": result.citations}


@server.tool()
async def list_documents() -> dict:
    """List all documents you have uploaded."""
    account_id = get_account_id()
    with SessionLocal() as db:
        docs = document_service.list_documents(account_id, db)
    return {"documents": [d.__dict__ for d in docs]}


@server.tool()
async def delete_document(document_id: str) -> dict:
    """Delete a document and all its chunks."""
    account_id = get_account_id()
    storage = get_storage_service()
    with SessionLocal() as db:
        document_service.delete_document(document_id, account_id, db, storage)
    return {"deleted": document_id}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()

    if args.transport == "stdio":
        import asyncio
        asyncio.run(stdio_server(server))
    else:
        # HTTP/SSE transport
        import uvicorn
        from mcp.server.sse import SseServerTransport
        # Wire up SSE transport on /mcp endpoint
        # ... (see MCP SDK docs for HTTP wiring)
        pass
```

**pyproject.toml entry point**:

```toml
[project.scripts]
rag-mcp = "app.mcp_server:main"
```

This allows: `uv run rag-mcp` or `uv run rag-mcp --transport http --port 8001`

**Docker Compose addition** (HTTP transport only):

```yaml
# docker-compose.yml addition
mcp:
  build: .
  command: uv run rag-mcp --transport http --port 8001
  ports:
    - "8001:8001"
  env_file: .env
  depends_on:
    - postgres
```

---

## MCP Client Configuration

### Claude Desktop (stdio)

```json
// ~/.config/claude/claude_desktop_config.json
{
  "mcpServers": {
    "rag-api": {
      "command": "uv",
      "args": ["--directory", "/path/to/rag-api", "run", "rag-mcp"],
      "env": {
        "MCP_AUTH_TOKEN": "<your-jwt-token>",
        "DATABASE_URL": "postgresql://rag:rag@localhost:5432/rag",
        "OPENAI_API_KEY": "<your-key>",
        "JWT_SECRET": "<your-secret>"
      }
    }
  }
}
```

### Claude Code (stdio)

Add to `.claude/settings.json` in the project or user config:
```json
{
  "mcpServers": {
    "rag-api": {
      "command": "uv",
      "args": ["--directory", "/path/to/rag-api", "run", "rag-mcp"],
      "env": {
        "MCP_AUTH_TOKEN": "<your-jwt-token>",
        "DATABASE_URL": "postgresql://rag:rag@localhost:5432/rag",
        "OPENAI_API_KEY": "<your-key>",
        "JWT_SECRET": "<your-secret>"
      }
    }
  }
}
```

### HTTP Transport (remote)

```json
{
  "mcpServers": {
    "rag-api": {
      "url": "http://your-server:8001/mcp",
      "headers": {
        "Authorization": "Bearer <your-jwt-token>"
      }
    }
  }
}
```

---

## Tool Schemas

These schemas are what MCP-compatible clients will see when they introspect your server.

### `upload_document`
```json
{
  "name": "upload_document",
  "description": "Upload a document to your RAG knowledge base. The document will be chunked and embedded automatically.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "filename": {"type": "string", "description": "Original filename including extension (.txt, .md, .pdf)"},
      "content_b64": {"type": "string", "description": "Base64-encoded file content"}
    },
    "required": ["filename", "content_b64"]
  }
}
```

### `query_documents`
```json
{
  "name": "query_documents",
  "description": "Ask a question and get an answer grounded in your uploaded documents.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "question": {"type": "string"},
      "top_k": {"type": "integer", "default": 5, "description": "Number of chunks to retrieve"}
    },
    "required": ["question"]
  }
}
```

### `list_documents`
```json
{
  "name": "list_documents",
  "description": "List all documents in your knowledge base.",
  "inputSchema": {"type": "object", "properties": {}}
}
```

### `delete_document`
```json
{
  "name": "delete_document",
  "description": "Delete a document and all its chunks from your knowledge base.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "document_id": {"type": "string", "description": "UUID of the document to delete"}
    },
    "required": ["document_id"]
  }
}
```

---

## API Changes

The REST API is unchanged. The MCP server is a new entry point.

Two processes can run simultaneously:
- `uvicorn app.main:app --port 8000` — REST API
- `uv run rag-mcp --transport http --port 8001` — MCP server (HTTP transport)

Or just the MCP server in stdio mode (no HTTP port needed).

---

## Test Requirements

Create `tests/test_mcp_server.py`:

- `test_upload_document_tool` — call the `upload_document` tool function directly with a small base64-encoded text file; assert `document_id` returned and document exists in DB
- `test_query_documents_tool` — upload a doc, call `query_documents`; assert `answer` and `citations` in response
- `test_list_documents_tool` — upload two docs; call `list_documents`; assert both returned
- `test_delete_document_tool` — upload a doc; call `delete_document`; assert document gone from DB
- `test_upload_invalid_token` — monkeypatch `MCP_AUTH_TOKEN` to garbage value; assert `AuthError` raised
- `test_cross_tenant_isolation` — upload doc as acct_A; monkeypatch token to acct_B; call `query_documents`; assert answer reflects no documents found (not acct_A's data)

**Testing notes**:
- Test the tool functions directly (not via MCP protocol wire format) for simplicity
- Mock OpenAI calls as per Phase 1 test patterns
- Set `MCP_AUTH_TOKEN` via monkeypatch in each test, not via env directly

---

## Acceptance Criteria

- [ ] `uv run rag-mcp` starts without error in stdio mode
- [ ] `uv run rag-mcp --transport http` starts and responds on port 8001
- [ ] `upload_document` tool successfully ingests a document and returns `document_id`
- [ ] `query_documents` tool returns a grounded answer using only the caller's documents
- [ ] `list_documents` tool returns only the caller's documents
- [ ] `delete_document` tool removes the document and all its chunks
- [ ] An invalid `MCP_AUTH_TOKEN` causes tool calls to fail with a clear auth error
- [ ] Claude Desktop / Claude Code can be configured to connect to the server (manual verification)
- [ ] `make test` passes
- [ ] `make lint && make typecheck` passes

---

## Validation Steps

```bash
# Generate a token
JWT_SECRET=dev-secret uv run python scripts/generate_token.py acct_001

# Test stdio server (interactive)
MCP_AUTH_TOKEN=<token> DATABASE_URL=postgresql://rag:rag@localhost:5432/rag \
  OPENAI_API_KEY=<key> JWT_SECRET=dev-secret \
  uv run rag-mcp
# Send JSON-RPC via stdin to test tool calls

# Test HTTP server
uv run rag-mcp --transport http --port 8001 &
curl http://localhost:8001/mcp  # should return MCP capability handshake

make test
make lint
make typecheck
```

---

## Risks

- `mcp` SDK version pinning: the MCP protocol is evolving. Pin to a specific version and document it. Check `mcp` PyPI for the latest stable release.
- `upload_document` via base64 has a size limit concern: base64 encoding inflates files by ~33%. For a 50MB file, that's ~67MB in the JSON payload. Consider adding a file size check and returning a clear error if content exceeds a configurable `MAX_UPLOAD_SIZE_MB` limit.
- Async context: the MCP SDK is async; the existing service layer is synchronous. Wrap sync service calls with `asyncio.to_thread()` or run them directly if the event loop overhead is acceptable.
- HTTP transport auth: for HTTP MCP, the Bearer token must come from the MCP request headers, not `MCP_AUTH_TOKEN` env var. The `get_account_id()` function needs to handle both cases — refactor to accept an optional token parameter.
- The `ingestion.ingest_document_from_bytes()` function may not exist yet — if the existing `ingest_document` only accepts `UploadFile`, add a bytes variant.

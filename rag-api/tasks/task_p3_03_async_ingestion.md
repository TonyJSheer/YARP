# Task P3-03 — Async Ingestion (Redis + Worker)

**Type**: `feature`
**Priority**: P1

**Summary**: Move document ingestion off the upload request thread. `upload_document` returns immediately with `status: processing`. A Redis-backed worker processes the job in the background. A new `get_document_status` MCP tool and `GET /documents/{id}` REST endpoint let callers poll for completion.

**Depends on**: P3-02 (cloud deployment adds Redis to the stack)

---

## Context

**The problem**: Ingestion (text extraction → chunking → embedding) is synchronous on upload. For large PDFs this takes 30–60 seconds, blocking the HTTP request and causing MCP tool call timeouts.

**Approach**: Simple Redis list queue. No Celery, no complex job DSL — just `LPUSH` on upload and `BRPOP` in the worker. This is intentionally minimal.

---

## Requirements

**Functional**:
- `upload_document` (MCP) and `POST /documents` (REST) return immediately with `status: processing` and a `document_id`
- A background worker process picks up jobs from a Redis list and runs the ingestion pipeline
- `get_document_status(document_id)` MCP tool returns current status (`processing`, `ready`, `failed`)
- `GET /documents/{id}` REST endpoint returns document detail including current status
- If ingestion fails, `document.status` is set to `failed` with an error message stored
- Worker retries once on transient failures (embedding API timeout); marks as `failed` after second failure

**Non-functional**:
- Worker is a separate process: `python -m app.worker`
- `docker-compose.yml` gains `redis` and `worker` services
- `fly.toml` gains a `worker` process group
- Worker is stateless — multiple workers can run in parallel safely (each job is atomic)

---

## Implementation Guidelines

**New packages** (via `uv add`):
- `redis>=5.0` — Redis client

**Files to create**:
- `app/worker.py` — worker entry point; loops on `BRPOP`, calls `ingestion.ingest_job()`
- `app/services/job_queue.py` — `enqueue(doc_id)`, `dequeue()` wrappers

**Files to modify**:
- `app/models/document.py` — add `error_message: str | None` column
- `app/services/ingestion.py` — split into `enqueue_ingest()` (fast path, called by router) and `run_ingest_job()` (called by worker)
- `app/routers/documents.py` — call `enqueue_ingest()` instead of `ingest()`; add `GET /documents/{id}`
- `app/mcp_server.py` — add `get_document_status` tool
- `app/config.py` — add `redis_url: str = "redis://localhost:6379/0"`
- `docker-compose.yml` — add `redis` and `worker` services
- `fly.toml` — add `worker` process group
- `migrations/versions/` — new migration for `error_message` column

**Job queue sketch**:

```python
# app/services/job_queue.py
import redis
from app.config import settings

QUEUE_KEY = "rag:ingest:queue"

def _client() -> redis.Redis:  # type: ignore[type-arg]
    return redis.from_url(settings.redis_url, decode_responses=True)

def enqueue(document_id: str) -> None:
    _client().lpush(QUEUE_KEY, document_id)

def dequeue(timeout: int = 5) -> str | None:
    """Block for up to `timeout` seconds. Returns document_id or None."""
    result = _client().brpop(QUEUE_KEY, timeout=timeout)
    return result[1] if result else None
```

**Worker sketch**:

```python
# app/worker.py
"""Ingestion worker — processes jobs from the Redis queue.

Run: python -m app.worker
"""
import logging
import signal
import sys

from app.services import job_queue, ingestion
from app.db import SessionLocal

logger = logging.getLogger(__name__)
_running = True

def _shutdown(sig, frame):  # type: ignore[no-untyped-def]
    global _running
    logger.info("Shutdown signal received")
    _running = False

signal.signal(signal.SIGTERM, _shutdown)
signal.signal(signal.SIGINT, _shutdown)

def main() -> None:
    logger.info("Worker started")
    while _running:
        doc_id = job_queue.dequeue(timeout=5)
        if doc_id is None:
            continue
        logger.info("Processing document %s", doc_id)
        try:
            with SessionLocal() as db:
                ingestion.run_ingest_job(doc_id, db)
            logger.info("Document %s ingested successfully", doc_id)
        except Exception:
            logger.exception("Ingestion failed for document %s", doc_id)

if __name__ == "__main__":
    main()
```

**Updated ingestion flow**:

```python
# app/services/ingestion.py

def enqueue_ingest(file: UploadFile, account_id: str, db: Session) -> uuid.UUID:
    """Save file and create document record, then enqueue the ingestion job.
    Returns document_id immediately with status='processing'.
    """
    doc, _ = save_and_record(file, account_id, db)
    doc.status = "processing"
    db.commit()
    job_queue.enqueue(str(doc.id))
    return doc.id

def run_ingest_job(document_id: str, db: Session) -> None:
    """Called by the worker. Runs extract → chunk → embed → store."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise ValueError(f"Document {document_id} not found")
    # ... existing pipeline ...
    # On failure: doc.status = "failed"; doc.error_message = str(exc)
```

**New MCP tool**:

```python
@mcp.tool()
async def get_document_status(document_id: str) -> dict[str, Any]:
    """Check the ingestion status of a document.

    Returns status: 'processing' | 'ready' | 'failed'
    Poll this after upload_document until status is 'ready'.
    """
    account_id = get_account_id()

    def _run() -> dict[str, Any]:
        from app.db import SessionLocal
        with SessionLocal() as db:
            doc = document_service.get_document(document_id, account_id, db)
            if doc is None:
                raise ValueError("not_found")
        return {"document_id": document_id, "status": doc.status, "error": doc.error_message}

    return await asyncio.to_thread(_run)
```

**docker-compose.yml additions**:

```yaml
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

  worker:
    build: .
    command: python -m app.worker
    env_file: .env
    environment:
      - DATABASE_URL=postgresql://rag:rag@postgres:5432/rag
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
```

**fly.toml addition**:

```toml
[processes]
  api    = "uv run uvicorn app.main:app --host 0.0.0.0 --port 8000"
  mcp    = "uv run rag-mcp --transport http --host 0.0.0.0 --port 8001"
  worker = "python -m app.worker"
```

---

## API Changes

`POST /documents` response changes to:
```json
{"document_id": "...", "status": "processing"}
```
(was `"status": "ready"` — now always `"processing"` on upload)

New endpoint:
`GET /documents/{id}` — returns document detail:
```json
{
  "document_id": "...",
  "filename": "report.pdf",
  "status": "ready",
  "created_at": "...",
  "chunk_count": 42,
  "error_message": null
}
```

New MCP tool: `get_document_status(document_id)`

---

## Test Requirements

- `test_upload_returns_processing_immediately` — upload a document; assert `status == "processing"` in response (does not wait for ingestion)
- `test_worker_processes_job` — enqueue a doc_id manually; run `run_ingest_job()` directly; assert status becomes `"ready"` and chunks exist
- `test_worker_marks_failed_on_error` — mock embedding to raise; run job; assert `status == "failed"` and `error_message` is set
- `test_get_document_status_mcp_tool` — assert `get_document_status` returns correct status for a known document
- `test_get_document_status_wrong_account` — assert 404 for another account's document

**Note**: Do not test the worker's Redis polling loop in unit tests — test `run_ingest_job()` directly. The queue itself is tested via `enqueue`/`dequeue` against a real or mocked Redis.

---

## Acceptance Criteria

- [ ] `POST /documents` returns `status: processing` immediately (no waiting for ingestion)
- [ ] Worker picks up job and completes ingestion; document becomes `status: ready`
- [ ] `get_document_status` MCP tool reports correct status
- [ ] Failed ingestion sets `status: failed` with `error_message` populated
- [ ] `docker compose up` starts redis + worker alongside api + postgres
- [ ] `make test` passes
- [ ] `make lint && make typecheck` passes

---

## Risks

- `BRPOP` timeout: if Redis goes away, the worker loop should handle `ConnectionError` gracefully (log, sleep briefly, retry)
- Duplicate jobs: if the same doc_id is enqueued twice (e.g., retry after failure), `run_ingest_job` should check current status first and skip if already `ready`
- Existing tests that assert `status: ready` on upload will break — update them to assert `status: processing`

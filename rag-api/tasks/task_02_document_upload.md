# Task 02 — Document Upload API

**Type**: `feature`

**Summary**: Implement `POST /documents` — accept a multipart file upload, save it to local disk, create a `documents` record in the database, and return the document ID with status `uploaded`. This is purely the upload step; chunking and embedding come in Tasks 03–05.

---

## Context

**Background**: The router stub exists at `app/routers/documents.py` and the partial ingestion service exists at `app/services/ingestion.py`. The `documents` table is live (Task 01). This task wires them together for the upload-only step.

**Affected components**:
- [x] Backend API
- [x] Database schema (no changes — documents table already exists)

---

## Requirements

**Functional**:
- `POST /documents` accepts a multipart file upload
- File is saved to `UPLOAD_DIR` (from `config.settings.upload_dir`) with a UUID prefix to avoid name collisions
- sha256 of the file content is computed and stored
- A record is inserted into the `documents` table with `status = "uploaded"`
- Response: `201 {"document_id": "<uuid>", "status": "uploaded"}`
- Unsupported file types (anything other than `.txt`, `.md`, `.pdf`) return `400` with the standard error envelope

**Non-functional**:
- `UPLOAD_DIR` must be created if it does not exist
- File is streamed to disk in chunks — do not load the entire file into memory

---

## Implementation Guidelines

**Files to modify**:
- `app/services/ingestion.py` — implement `save_and_record(file, db)` using the existing `_save_file()` stub
- `app/routers/documents.py` — call `ingestion.save_and_record(file, db)`, return response

**Files to create**:
- `tests/test_documents.py` — upload endpoint tests

**Architecture constraints**:
- Business logic stays in `app/services/ingestion.py` — the router only calls the service and returns the response
- Use `response_model=None` on the route decorator (FastAPI cannot validate msgspec Structs) and return a plain `dict` or `Response` with msgspec-encoded bytes
- Do not start chunking or embedding in this task — `status` stays `"uploaded"` on return
- Validate file extension before saving — raise `HTTPException(400, ...)` for unsupported types

**Implementation sketch**:

```python
# app/services/ingestion.py

SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf"}

def save_and_record(file: UploadFile, db: Session) -> Document:
    # 1. Validate extension
    # 2. Call _save_file(file) → (path, sha256)
    # 3. Insert Document(filename, content_type, sha256, status="uploaded")
    # 4. db.commit(), db.refresh(doc)
    # 5. Return doc
```

```python
# app/routers/documents.py

@router.post("", status_code=201, response_model=None)
async def upload_document(file: UploadFile, db: Session = Depends(get_db)) -> dict:
    doc = ingestion.save_and_record(file, db)
    return {"document_id": str(doc.id), "status": doc.status}
```

---

## API Changes

**Endpoint**: `POST /documents`

**Request**: `multipart/form-data` with field `file`

**Response** `201`:
```json
{
  "document_id": "3f7a1b2c-...",
  "status": "uploaded"
}
```

**Error** `400` (unsupported file type):
```json
{
  "error": {
    "code": "unsupported_file_type",
    "message": "Only .txt, .md, and .pdf files are supported",
    "field": "file"
  }
}
```

---

## Test Requirements

Create `tests/test_documents.py`:

- `test_upload_txt_returns_201` — upload a small `.txt` file, assert 201, assert `document_id` is a UUID string, assert `status == "uploaded"`
- `test_upload_creates_db_record` — after upload, query the DB and confirm the documents row exists with correct filename and sha256
- `test_upload_unsupported_type_returns_400` — upload a `.exe` file, assert 400 and error code `unsupported_file_type`
- `test_upload_saves_file_to_disk` — after upload, confirm the file exists on disk in `UPLOAD_DIR`

**Testing notes**:
- Override the `get_db` dependency in conftest to use a test DB session (or mock it)
- Override `settings.upload_dir` to a temp directory in tests so files don't accumulate in `./data/uploads`
- Use `pytest` `tmp_path` fixture for the upload directory

---

## Acceptance Criteria

- [ ] `POST /documents` with a `.txt` file returns `201 {"document_id": "...", "status": "uploaded"}`
- [ ] File appears on disk in `UPLOAD_DIR` after upload
- [ ] A row appears in the `documents` table with correct `filename`, `content_type`, `sha256`, `status = "uploaded"`
- [ ] `POST /documents` with an unsupported file type returns `400`
- [ ] `make test` passes
- [ ] `make lint && make typecheck` passes with no new errors

---

## Validation Steps

```bash
# Start services
docker compose up postgres -d
make migrate

# Manual smoke test
curl -X POST http://localhost:8000/documents \
  -F "file=@/path/to/test.txt"
# Expected: {"document_id": "...", "status": "uploaded"}

# Verify DB record
docker compose exec postgres psql -U rag -d rag -c "SELECT id, filename, status FROM documents;"

# Run test suite
make test
make lint
make typecheck
```

---

## Risks

- `UploadFile.file` is a `SpooledTemporaryFile` — reads must be done before the file handle closes; `_save_file` reads it in the same call so this is safe
- Concurrent uploads to the same `UPLOAD_DIR` are safe because each file gets a UUID prefix
- The `content_type` field comes from `file.content_type` which is browser-supplied and not validated — this is acceptable for Phase 1

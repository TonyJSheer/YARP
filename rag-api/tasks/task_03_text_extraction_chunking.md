# Task 03 — Text Extraction + Chunking

**Type**: `feature`

**Summary**: Implement text extraction from `.txt`, `.md`, and `.pdf` files and a sentence-aware chunking algorithm. Extend the ingestion pipeline to extract, chunk, and store `Chunk` rows after a document is uploaded. After this task, uploading a document produces chunk rows in the database (with `embedding=None`; embeddings come in Task 04).

---

## Context

**Background**: Task 02 implemented the upload step — files are saved to disk and a `documents` row is created with `status='uploaded'`. The router currently calls `save_and_record()`. This task extends `ingest()` to run the extraction and chunking pipeline, then updates the router to call `ingest()` instead. The `chunking.py` service has function stubs with the constants already defined. `pypdf` is already installed.

**Affected components**:
- [x] Backend API
- [x] Database schema (no changes — `chunks` table already exists)

---

## Requirements

**Functional**:
- `extract_text(file_path)` extracts text from `.txt`, `.md`, `.pdf` files
  - `.txt` / `.md`: read as UTF-8, return as a single page with `page_number=None`
  - `.pdf`: extract per page using `pypdf`, return one entry per non-empty page with `page_number` set (1-indexed)
- `chunk_text(text)` splits a string into overlapping chunks
  - Target chunk size: `TARGET_CHARS` (~2800 chars / ~700 tokens)
  - Overlap: `OVERLAP_CHARS` (~320 chars / ~80 tokens)
  - Sentence-boundary aware: split at sentence endings (`.`, `!`, `?`) where possible
- `ingest()` in `ingestion.py` is extended to:
  1. Call `save_and_record()` → creates `documents` row with `status='uploaded'`
  2. Set `doc.status = 'processing'`, commit
  3. Call `extract_text(saved_file_path)` → `(texts, page_numbers)`
  4. For each page, call `chunk_text(text)` → list of chunk strings
  5. Insert `Chunk` rows (`embedding=None`) for all chunks across all pages
  6. Set `doc.status = 'chunked'`, commit
  7. Return `doc.id`
- `POST /documents` router updated to call `ingest()` instead of `save_and_record()`
- On extraction failure (e.g. corrupted PDF): set `doc.status = 'failed'`, commit, raise `HTTPException(422)`

**Non-functional**:
- `chunk_index` is a global sequential index across all pages of the document (not per-page)
- Empty chunks (whitespace only) are discarded
- `Chunk.metadata_` can be left as `None` for Phase 1

---

## Implementation Guidelines

**Files to modify**:
- `app/services/chunking.py` — implement `extract_text()` and `chunk_text()`
- `app/services/ingestion.py` — extend `ingest()` with extraction + chunking + chunk storage
- `app/routers/documents.py` — call `ingest()` instead of `save_and_record()`

**Files to modify (tests)**:
- `tests/test_chunking.py` — replace stubs with real tests
- `tests/test_documents.py` — update `test_upload_txt_returns_201` status assertion; add integration test for chunk creation

**Implementation sketch — `chunking.py`**:

```python
import re
from pathlib import Path

def extract_text(file_path: str) -> tuple[list[str], list[int | None]]:
    path = Path(file_path)
    ext = path.suffix.lower()
    if ext in {".txt", ".md"}:
        text = path.read_text(encoding="utf-8", errors="replace")
        return [text], [None]
    elif ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        texts, page_numbers = [], []
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            if text.strip():
                texts.append(text)
                page_numbers.append(i + 1)
        return texts, page_numbers
    raise ValueError(f"Unsupported file type: {ext}")

def chunk_text(text: str) -> list[str]:
    # Split into sentences, then accumulate into chunks respecting TARGET_CHARS.
    # When a chunk would exceed the target, emit it and seed the next chunk
    # with the trailing OVERLAP_CHARS of content for continuity.
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    chunks: list[str] = []
    current: list[str] = []
    current_len: int = 0

    for sentence in sentences:
        s_len = len(sentence)
        if current_len + s_len > TARGET_CHARS and current:
            chunks.append(" ".join(current))
            # Seed next chunk with overlap from the tail of the current chunk
            overlap, overlap_len = [], 0
            for s in reversed(current):
                overlap_len += len(s)
                overlap.insert(0, s)
                if overlap_len >= OVERLAP_CHARS:
                    break
            current, current_len = overlap, sum(len(s) for s in overlap)
        current.append(sentence)
        current_len += s_len

    if current:
        chunks.append(" ".join(current))

    return [c for c in chunks if c.strip()]
```

**Implementation sketch — `ingestion.py` `ingest()`**:

```python
def ingest(file: UploadFile, db: Session) -> uuid.UUID:
    doc = save_and_record(file, db)

    doc.status = "processing"
    db.commit()

    try:
        texts, page_numbers = chunking.extract_text(str(saved_path))
        chunk_models = []
        for page_text, page_num in zip(texts, page_numbers):
            for chunk_str in chunking.chunk_text(page_text):
                chunk_models.append(Chunk(
                    document_id=doc.id,
                    chunk_index=len(chunk_models),
                    page_number=page_num,
                    text=chunk_str,
                    embedding=None,
                ))
        db.add_all(chunk_models)
        doc.status = "chunked"
        db.commit()
    except Exception:
        doc.status = "failed"
        db.commit()
        raise

    return doc.id
```

Note: `save_and_record()` currently doesn't return the saved file path. Either:
- Return `(doc, path)` from `save_and_record()` — **preferred**, clean
- Re-derive the path from `UPLOAD_DIR` by querying the doc — less clean

Update `save_and_record()` to return `tuple[Document, Path]` and update `ingest()` accordingly. Update `upload_document` in the router which currently unpacks just the `Document`.

**Router update**:

```python
@router.post("", status_code=201, response_model=None)
async def upload_document(file: UploadFile, db: Session = Depends(get_db)) -> ...:
    try:
        doc_id = ingestion.ingest(file, db)
    except ingestion.UnsupportedFileTypeError:
        return JSONResponse(status_code=400, content={...})
    except Exception:
        return JSONResponse(status_code=422, content={
            "error": {"code": "ingestion_failed", "message": "...", "field": None}
        })
    return {"document_id": str(doc_id), "status": "chunked"}
```

---

## API Changes

**Endpoint**: `POST /documents` (existing)

Response status field changes from `"uploaded"` → `"chunked"` after this task.

No other API changes.

---

## Test Requirements

**`tests/test_chunking.py`** — replace all stubs with real tests:

- `test_chunk_text_single_short_string` — text shorter than TARGET_CHARS returns one chunk equal to the input
- `test_chunk_text_respects_target_size` — each chunk (except possibly the last) is ≤ TARGET_CHARS + longest sentence
- `test_chunk_text_produces_overlap` — text of `text[i]` is contained (approximately) in `text[i+1]` for consecutive chunks
- `test_chunk_text_no_empty_chunks` — no empty or whitespace-only strings in output
- `test_extract_text_txt` — write a `.txt` file to `tmp_path`, assert extracted text matches content, page is `None`
- `test_extract_text_md` — same for `.md` file
- `test_extract_text_pdf` — create a minimal PDF with `pypdf` or use a test fixture; assert extracted text is non-empty and page numbers are 1-indexed

**`tests/test_documents.py`** additions:

- Update `test_upload_txt_returns_201`: change `status == "uploaded"` → `status == "chunked"`
- `test_upload_creates_chunk_rows` — upload a `.txt` file, query `chunks` table, assert at least one row exists with correct `document_id` and non-empty `text`, and `embedding IS NULL`

---

## Acceptance Criteria

- [ ] Uploading a `.txt` file via `POST /documents` returns `{"document_id": "...", "status": "chunked"}`
- [ ] At least one `Chunk` row exists in the DB with correct `document_id` after upload
- [ ] `Chunk.embedding` is `NULL` (not yet filled — Task 04)
- [ ] `documents.status` is `"chunked"` after successful ingestion
- [ ] Uploading a file that fails extraction sets `documents.status = "failed"` and returns `422`
- [ ] `make test` passes
- [ ] `make lint && make typecheck` passes with no new errors

---

## Validation Steps

```bash
# Manual smoke test
docker compose up postgres -d
make migrate

curl -X POST http://localhost:8000/documents \
  -F "file=@/path/to/test.txt"
# Expected: {"document_id": "...", "status": "chunked"}

# Verify chunks exist
docker compose exec postgres psql -U rag -d rag \
  -c "SELECT document_id, chunk_index, page_number, LEFT(text, 60) FROM chunks LIMIT 5;"

# Run test suite
make test
make lint
make typecheck
```

---

## Risks

- `save_and_record()` returns only `Document` — needs to also return the saved `Path` so `ingest()` can pass it to `extract_text()`. Refactor the return type to `tuple[Document, Path]` and update all callers.
- `test_upload_txt_returns_201` in `test_documents.py` currently asserts `status == "uploaded"` — **must be updated** to `status == "chunked"`.
- `test_upload_creates_db_record` in `test_documents.py` asserts `status == "uploaded"` — **must be updated** to `status == "chunked"`.
- pypdf's `extract_text()` may return empty strings for image-based PDFs — the empty-page filter in `extract_text()` handles this; no need to raise an error.
- Large files (e.g. 50MB PDF) will block the request thread — known limitation noted in ARCHITECTURE.md, acceptable in Phase 1.

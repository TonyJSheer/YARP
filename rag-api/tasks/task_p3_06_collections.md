# Task P3-06 — Collections + Enhanced Document Management

**Type**: `feature`
**Priority**: P2

**Summary**: Add named collections to group documents, expand supported file formats (.docx, .html, .csv), add document metadata, and add a `reindex_document` tool for re-embedding with an updated model.

**Depends on**: P3-01, P3-02

---

## Context

As a knowledge base grows, users need to organise documents into logical groups (e.g., "legal-docs", "product-specs", "meeting-notes") and query within a specific group. This task also adds practical quality-of-life features: more file formats and the ability to re-embed documents after changing the embedding model.

---

## Part 1: Collections

### Requirements

- `documents.collection TEXT NOT NULL DEFAULT 'default'` — new column
- All tools and endpoints accept an optional `collection` parameter (default: `"default"`)
- Queries are scoped to a collection when specified
- New MCP tool: `list_collections()` — returns all collection names and document counts for the account
- New REST endpoint: `GET /collections`

### Migration

```python
# migrations/versions/0006_add_collection.py
def upgrade() -> None:
    op.add_column("documents", sa.Column("collection", sa.Text(), nullable=False, server_default="default"))
    op.alter_column("documents", "collection", server_default=None)
    op.create_index("ix_documents_collection", "documents", ["account_id", "collection"])

def downgrade() -> None:
    op.drop_index("ix_documents_collection", table_name="documents")
    op.drop_column("documents", "collection")
```

### API + MCP changes

```python
# upload_document MCP tool — add collection param
async def upload_document(
    filename: str,
    content_b64: str,
    collection: str = "default",
) -> dict[str, Any]: ...

# query_documents MCP tool — add collection param
async def query_documents(
    question: str,
    top_k: int = 5,
    search_mode: str = "hybrid",
    rerank: bool = False,
    collection: str | None = None,  # None = search all collections
) -> dict[str, Any]: ...

# list_collections MCP tool
async def list_collections() -> dict[str, Any]:
    """List all collections in your knowledge base with document counts."""
    ...
    return {"collections": [{"name": "legal-docs", "document_count": 12}, ...]}
```

Retrieval scoping:
```python
# app/services/retrieval.py
# When collection is not None, add to WHERE clause:
# AND d.collection = :collection
```

---

## Part 2: Additional File Formats

### Supported formats after this task

| Extension | Parser |
|---|---|
| `.txt` | built-in (Phase 1) |
| `.md` | built-in (Phase 1) |
| `.pdf` | pypdf (Phase 1) |
| `.docx` | python-docx (new) |
| `.html` | beautifulsoup4 (new) |
| `.csv` | stdlib csv (new) |

### New packages

```bash
uv add python-docx beautifulsoup4
```

### Chunking service additions

```python
# app/services/chunking.py

def extract_text(file_path: str) -> tuple[list[str], list[int]]:
    """Returns (texts_per_page, page_numbers). Dispatch by extension."""
    ext = Path(file_path).suffix.lower()
    if ext == ".pdf":
        return _extract_pdf(file_path)
    elif ext == ".docx":
        return _extract_docx(file_path)
    elif ext == ".html":
        return _extract_html(file_path)
    elif ext == ".csv":
        return _extract_csv(file_path)
    else:
        # .txt and .md — plain text
        return _extract_text(file_path)


def _extract_docx(file_path: str) -> tuple[list[str], list[int]]:
    from docx import Document
    doc = Document(file_path)
    text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    return [text], [1]


def _extract_html(file_path: str) -> tuple[list[str], list[int]]:
    from bs4 import BeautifulSoup
    with open(file_path, encoding="utf-8", errors="replace") as f:
        soup = BeautifulSoup(f.read(), "html.parser")
    text = soup.get_text(separator="\n", strip=True)
    return [text], [1]


def _extract_csv(file_path: str) -> tuple[list[str], list[int]]:
    import csv
    rows: list[str] = []
    with open(file_path, newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(", ".join(f"{k}: {v}" for k, v in row.items()))
    # Each row is its own chunk — join in batches of 10
    chunks = ["\n".join(rows[i:i+10]) for i in range(0, len(rows), 10)]
    return chunks, list(range(1, len(chunks) + 1))
```

Update `SUPPORTED_EXTENSIONS` in `ingestion.py`:
```python
SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx", ".html", ".csv"}
```

---

## Part 3: Document Metadata

Allow arbitrary key-value metadata at upload time, stored as JSONB on the document record. Useful for filtering and attribution.

### Migration

```python
# migrations/versions/0007_add_document_metadata.py
def upgrade() -> None:
    op.add_column("documents", sa.Column("metadata", postgresql.JSONB(), nullable=True))

def downgrade() -> None:
    op.drop_column("documents", "metadata")
```

### MCP tool change

```python
async def upload_document(
    filename: str,
    content_b64: str,
    collection: str = "default",
    metadata: dict[str, str] | None = None,
) -> dict[str, Any]: ...
```

Metadata is stored on the document and returned in `list_documents`.

---

## Part 4: Re-index Document

When the `EMBED_MODEL` changes, existing embeddings are stale. `reindex_document` re-embeds all chunks for a document using the current model.

### New MCP tool

```python
@mcp.tool()
async def reindex_document(document_id: str) -> dict[str, Any]:
    """Re-embed all chunks for a document using the current embedding model.
    Use this after changing EMBED_MODEL. Returns chunk_count when complete.
    """
```

### Service implementation

```python
# app/services/document_service.py

def reindex_document(document_id: str, account_id: str, db: Session) -> int:
    """Re-embed all chunks. Returns chunk_count."""
    doc = db.query(Document).filter(
        Document.id == document_id,
        Document.account_id == account_id,
    ).first()
    if doc is None:
        raise DocumentNotFoundError()

    chunks = db.query(Chunk).filter(Chunk.document_id == doc.id).all()
    if not chunks:
        return 0

    vectors = embedding.embed_chunks([c.text for c in chunks])
    for chunk, vector in zip(chunks, vectors):
        chunk.embedding = vector

    db.commit()
    return len(chunks)
```

With async ingestion (P3-03), `reindex_document` should also go through the job queue for large documents.

---

## Test Requirements

**Collections**:
- `test_upload_with_collection` — upload with `collection="legal"`, list documents, assert collection is "legal"
- `test_query_scoped_to_collection` — upload doc in "A", upload doc in "B", query in "A", assert only "A"'s chunks returned
- `test_list_collections` — upload in two collections, call `list_collections`, assert both appear with correct counts

**File formats**:
- `test_docx_extraction` — upload a `.docx` file, assert chunks extracted
- `test_html_extraction` — upload a `.html` file, assert chunks extracted (no HTML tags in text)
- `test_csv_extraction` — upload a `.csv` file, assert chunks extracted from rows

**Metadata**:
- `test_upload_with_metadata` — upload with `metadata={"source": "Q4"}`, list docs, assert metadata returned
- `test_metadata_optional` — upload without metadata, assert no error

**Re-index**:
- `test_reindex_updates_embeddings` — mock embedding to return new vectors; call `reindex_document`; assert chunk embeddings updated
- `test_reindex_wrong_account_returns_404` — assert 404 when reindexing another account's doc

---

## Acceptance Criteria

- [ ] Collections: upload/query/list scoped by collection
- [ ] `list_collections` MCP tool returns collection names + counts
- [ ] `.docx`, `.html`, `.csv` files upload and index successfully
- [ ] `metadata` field stored and returned on documents
- [ ] `reindex_document` re-embeds all chunks with the current model
- [ ] Migrations apply cleanly
- [ ] `make test` passes
- [ ] `make lint && make typecheck` passes

---

## Risks

- `python-docx` reads `.docx` files but not `.doc` (old Word format). Document this clearly — `.doc` is not supported.
- HTML extraction with BeautifulSoup may pull in large amounts of boilerplate (nav menus, footers) — consider stripping `<nav>`, `<footer>`, `<script>`, `<style>` tags before extracting text.
- CSV files with many columns produce very long "rows" — the 10-row batching mitigates this but test with wide CSVs.
- `reindex_document` is synchronous (blocking) for large documents. If P3-03 (async ingestion) is complete, route it through the job queue instead.

# Task P2-04 — Document Management Endpoints (List + Delete)

**Type**: `feature`

**Summary**: Add `GET /documents` (list all documents owned by the caller) and `DELETE /documents/{document_id}` (delete a document, its chunks, and its stored file). Both endpoints are scoped to the authenticated `account_id`.

**Depends on**: P2-01, P2-02, P2-03

---

## Context

**Background**: Phase 1 had no way to list or delete documents — you could only upload and query. For the MCP server (P2-05), the `list_documents` and `delete_document` tools need real endpoints backing them. Auth and account scoping must already be in place.

**Affected components**:
- [x] Backend API (new routes)
- [x] Service layer (new `document_service.py` or additions to `ingestion.py`)
- [x] Schemas (new response types)

---

## Requirements

**Functional**:

`GET /documents`
- Returns a list of all documents owned by `account_id` (from auth token)
- Each item: `document_id`, `filename`, `status`, `created_at`, `chunk_count`
- Sorted by `created_at DESC`
- Returns empty list `[]` if no documents exist — not a 404

`DELETE /documents/{document_id}`
- Deletes the document record, all associated chunk records, and the stored file
- If document does not exist → `404` with standard error envelope
- If document belongs to a different `account_id` → `404` (do not reveal existence of other tenants' data)
- On success → `204 No Content`

**Non-functional**:
- Deletion is atomic at the DB level (chunks cascade via FK, document deleted in same transaction)
- File deletion from storage happens after the DB transaction commits (if file delete fails, log the error but do not roll back — the DB record is the source of truth)

---

## Implementation Guidelines

**Files to create**:
- `app/services/document_service.py` — `list_documents(account_id, db)` and `delete_document(document_id, account_id, db, storage)`
- `app/schemas/document.py` additions — `DocumentListItem`, `DocumentListResponse`
- `tests/test_document_management.py`

**Files to modify**:
- `app/routers/documents.py` — add `GET /documents` and `DELETE /documents/{document_id}` routes

**Service implementation sketch**:

```python
# app/services/document_service.py

def list_documents(account_id: str, db: Session) -> list[DocumentListItem]:
    rows = (
        db.query(
            Document,
            func.count(Chunk.id).label("chunk_count")
        )
        .outerjoin(Chunk, Chunk.document_id == Document.id)
        .filter(Document.account_id == account_id)
        .group_by(Document.id)
        .order_by(Document.created_at.desc())
        .all()
    )
    return [
        DocumentListItem(
            document_id=str(doc.id),
            filename=doc.filename,
            status=doc.status,
            created_at=doc.created_at.isoformat(),
            chunk_count=count,
        )
        for doc, count in rows
    ]

def delete_document(
    document_id: str,
    account_id: str,
    db: Session,
    storage: StorageService,
) -> None:
    doc = db.query(Document).filter(
        Document.id == document_id,
        Document.account_id == account_id,
    ).first()

    if doc is None:
        raise DocumentNotFoundError()

    storage_key = doc.storage_key

    # Cascade delete handles chunks (FK ON DELETE CASCADE)
    db.delete(doc)
    db.commit()

    # Delete file after DB commit — non-fatal if it fails
    if storage_key:
        try:
            storage.delete(storage_key)
        except Exception:
            logger.error("Failed to delete storage key %s", storage_key)
```

**Router additions**:

```python
# app/routers/documents.py

@router.get("", response_model=None)
async def list_documents(
    account_id: str = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> dict:
    items = document_service.list_documents(account_id, db)
    return {"documents": [msgspec.to_builtins(item) for item in items]}

@router.delete("/{document_id}", status_code=204, response_model=None)
async def delete_document(
    document_id: str,
    account_id: str = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> None:
    storage = get_storage_service()
    try:
        document_service.delete_document(document_id, account_id, db, storage)
    except document_service.DocumentNotFoundError:
        raise HTTPException(404, detail={"error": {"code": "not_found", "message": "Document not found", "field": None}})
```

---

## API Changes

**New endpoints**:

`GET /documents` (requires auth)

Response `200`:
```json
{
  "documents": [
    {
      "document_id": "3f7a1b2c-...",
      "filename": "report.pdf",
      "status": "ready",
      "created_at": "2026-03-09T10:00:00Z",
      "chunk_count": 42
    }
  ]
}
```

`DELETE /documents/{document_id}` (requires auth)

Response `204`: No body.

Error `404`:
```json
{"error": {"code": "not_found", "message": "Document not found", "field": null}}
```

---

## Test Requirements

Create `tests/test_document_management.py`:

- `test_list_documents_returns_own_documents` — upload two docs as account A; call GET /documents as A; assert both returned
- `test_list_documents_does_not_return_other_accounts_documents` — upload doc as account A; call GET /documents as account B; assert empty list
- `test_list_documents_empty` — no uploads; GET /documents returns `{"documents": []}`
- `test_list_documents_includes_chunk_count` — upload and ingest doc; list; assert `chunk_count > 0`
- `test_delete_own_document_returns_204` — upload doc as A; delete as A; assert 204
- `test_delete_removes_chunks` — upload and ingest; delete; assert chunks table has no rows for that document_id
- `test_delete_other_accounts_document_returns_404` — upload as A; try delete as B; assert 404
- `test_delete_nonexistent_returns_404` — delete random UUID; assert 404

---

## Acceptance Criteria

- [ ] `GET /documents` returns only the caller's documents
- [ ] `GET /documents` returns `chunk_count` per document
- [ ] `DELETE /documents/{id}` removes document, all chunks, and stored file
- [ ] `DELETE /documents/{id}` for another account's document returns 404 (not 403)
- [ ] `make test` passes
- [ ] `make lint && make typecheck` passes

---

## Validation Steps

```bash
TOKEN_A=$(uv run python scripts/generate_token.py acct_001)
TOKEN_B=$(uv run python scripts/generate_token.py acct_002)

# Upload as A
curl -X POST http://localhost:8000/documents \
  -H "Authorization: Bearer $TOKEN_A" -F "file=@test.txt"

# List as A — should see the doc
curl http://localhost:8000/documents -H "Authorization: Bearer $TOKEN_A"

# List as B — should be empty
curl http://localhost:8000/documents -H "Authorization: Bearer $TOKEN_B"

# Delete as A
DOC_ID=<id from upload>
curl -X DELETE http://localhost:8000/documents/$DOC_ID \
  -H "Authorization: Bearer $TOKEN_A"
# Expected: 204

# Confirm deleted
docker compose exec postgres psql -U rag -d rag \
  -c "SELECT count(*) FROM documents;"

make test
```

---

## Risks

- `ON DELETE CASCADE` on `chunks.document_id` FK must have been applied in the original migration — verify this before relying on it. If not present, add it in a new migration `0004_add_cascade.py`.
- File deletion after DB commit: if the storage service raises, log and move on. This is a known trade-off (orphaned file vs. broken transaction). Could add a cleanup job later.
- The `chunk_count` subquery adds a JOIN to every list call — acceptable at Phase 2 scale.

# Task P2-03 — Storage Service Refactor (Account-Scoped + S3)

**Type**: `feature`

**Summary**: Introduce a `StorageService` abstraction with two implementations: `LocalStorageService` (existing behaviour, account-scoped paths) and `S3StorageService` (boto3, account-scoped S3 keys). Active backend is selected via `STORAGE_BACKEND=local|s3` config.

**Depends on**: P2-01 (account_id exists)
**Can be built in parallel with**: P2-02

---

## Context

**Background**: Phase 1 stored files directly to `./data/uploads/{uuid}_{filename}`. Phase 2 needs two changes: (1) scope storage paths by `account_id` so tenants can't accidentally reference each other's files, and (2) support S3 as an alternative backend for non-local deployments. The abstraction also makes tests easier — mock the interface, not the filesystem.

**Affected components**:
- [x] New module: `app/services/storage.py`
- [x] `app/services/ingestion.py` — use `StorageService` instead of direct file writes
- [x] Config (new S3 env vars)
- [x] Docker Compose (no changes needed for local backend)

---

## Requirements

**Functional**:
- `StorageService` protocol with methods:
  - `save(account_id: str, filename: str, data: bytes) -> str` — saves file, returns storage key/path
  - `delete(key: str) -> None` — deletes file by key
  - `get_url(key: str) -> str` — returns a usable path/URL (local path or S3 presigned URL)
- `LocalStorageService`:
  - Saves to `{UPLOAD_DIR}/{account_id}/{uuid}_{filename}`
  - Creates `{UPLOAD_DIR}/{account_id}/` directory if absent
  - `get_url` returns the absolute local path
- `S3StorageService`:
  - Saves to `s3://{S3_BUCKET}/{account_id}/{uuid}_{filename}`
  - Key returned is `{account_id}/{uuid}_{filename}` (no s3:// prefix — the bucket is implicit)
  - `get_url` returns a presigned URL (1-hour expiry) for the object
  - Uses boto3 with credentials from env (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `S3_REGION`)
- `get_storage_service() -> StorageService` — factory function; reads `STORAGE_BACKEND` from config and returns the appropriate instance
- `ingestion.py` calls `storage_service.save(account_id, filename, data)` instead of writing directly

**Non-functional**:
- S3 is optional — if `STORAGE_BACKEND=local`, boto3 is never imported
- Storage key is stored on the `documents` record so files can be found and deleted later
- Tests for `LocalStorageService` use `tmp_path`; tests for `S3StorageService` use `moto` (S3 mock)

---

## Implementation Guidelines

**New packages to add** (via `uv add`):
- `boto3` — S3 client
- `moto[s3]` — S3 mock for tests (dev/test group)

**Files to create**:
- `app/services/storage.py`

**Files to modify**:
- `app/config.py` — add `STORAGE_BACKEND: str = "local"`, `S3_BUCKET: str = ""`, `S3_REGION: str = "us-east-1"`, `AWS_ACCESS_KEY_ID: str = ""`, `AWS_SECRET_ACCESS_KEY: str = ""`
- `app/models/document.py` — add `storage_key: str` column (stores the path/key returned by `save()`)
- `app/services/ingestion.py` — use `get_storage_service()` instead of direct file writes
- `migrations/versions/0003_add_storage_key.py` — add `storage_key` column

**Storage service implementation sketch**:

```python
# app/services/storage.py
import uuid
from typing import Protocol
from pathlib import Path

class StorageService(Protocol):
    def save(self, account_id: str, filename: str, data: bytes) -> str: ...
    def delete(self, key: str) -> None: ...
    def get_url(self, key: str) -> str: ...

class LocalStorageService:
    def __init__(self, upload_dir: str) -> None:
        self.base = Path(upload_dir)

    def save(self, account_id: str, filename: str, data: bytes) -> str:
        dest_dir = self.base / account_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        key = f"{account_id}/{uuid.uuid4()}_{filename}"
        (self.base / key).write_bytes(data)
        return key

    def delete(self, key: str) -> None:
        path = self.base / key
        if path.exists():
            path.unlink()

    def get_url(self, key: str) -> str:
        return str(self.base / key)

class S3StorageService:
    def __init__(self, bucket: str, region: str) -> None:
        import boto3
        self.bucket = bucket
        self.client = boto3.client("s3", region_name=region)

    def save(self, account_id: str, filename: str, data: bytes) -> str:
        key = f"{account_id}/{uuid.uuid4()}_{filename}"
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data)
        return key

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def get_url(self, key: str) -> str:
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=3600,
        )

def get_storage_service() -> StorageService:
    from app.config import settings
    if settings.storage_backend == "s3":
        return S3StorageService(settings.s3_bucket, settings.s3_region)
    return LocalStorageService(settings.upload_dir)
```

**Ingestion change**:

```python
# app/services/ingestion.py
# Replace direct file write with:
storage = get_storage_service()
storage_key = storage.save(account_id, file.filename, file_data)
# Store storage_key on the Document record
```

---

## API Changes

None externally visible. The `storage_key` is an internal field stored on the document record.

Document response may optionally include `storage_key` in a later task (e.g. list_documents). Not required here.

---

## Test Requirements

Create `tests/test_storage.py`:

- `test_local_save_creates_file` — save a file, assert it exists at the expected path
- `test_local_save_scopes_by_account_id` — two accounts save files with same filename; assert they land in different directories
- `test_local_delete_removes_file` — save then delete; assert file is gone
- `test_local_get_url_returns_path` — assert `get_url` returns a valid path string
- `test_s3_save_uploads_object` (uses `moto`) — mock S3, save a file, assert object exists in bucket
- `test_s3_delete_removes_object` (uses `moto`) — save then delete, assert object gone
- `test_factory_returns_local_by_default` — override config `STORAGE_BACKEND=local`, assert `LocalStorageService` returned
- `test_factory_returns_s3_when_configured` — override config `STORAGE_BACKEND=s3`, assert `S3StorageService` returned

---

## Acceptance Criteria

- [ ] `LocalStorageService.save` creates files at `{UPLOAD_DIR}/{account_id}/{uuid}_{filename}`
- [ ] `S3StorageService.save` uploads to `s3://{bucket}/{account_id}/{uuid}_{filename}` key
- [ ] Files from different accounts are stored in separate paths — no cross-tenant file access possible
- [ ] `documents.storage_key` is populated on upload
- [ ] Switching `STORAGE_BACKEND=s3` (with valid S3 config) causes uploads to go to S3
- [ ] `make test` passes (S3 tests use moto mock, not real AWS)
- [ ] `make lint && make typecheck` passes

---

## Validation Steps

```bash
# Local storage test
make migrate
TOKEN=$(uv run python scripts/generate_token.py acct_001)
curl -X POST http://localhost:8000/documents \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@test.txt"

# Check scoped path
ls ./data/uploads/acct_001/

# Check storage_key in DB
docker compose exec postgres psql -U rag -d rag \
  -c "SELECT id, account_id, storage_key FROM documents;"

make test
make lint
make typecheck
```

---

## Risks

- `boto3` is a large dependency — lazy import it inside `S3StorageService.__init__` so it doesn't slow startup for `local` mode
- `moto` must be in the dev/test dependency group only — do not include in production deps
- `storage_key` migration must add the column as nullable first (existing rows have no key), then set NOT NULL after backfill if needed. For Phase 2, nullable is acceptable since old Phase 1 data is ephemeral dev data.
- Presigned URL expiry (1 hour) may be too short for some use cases — make it configurable later, hardcode for now
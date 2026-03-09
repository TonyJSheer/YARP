# Task P2-06 — Phase 2 Test Suite

**Type**: `testing`

**Summary**: Fill any gaps in the Phase 2 test coverage. Ensure all new Phase 2 features (auth, multi-tenancy, storage, document management, MCP server) have tests. Update CI to pass with the new `JWT_SECRET` and `STORAGE_BACKEND` environment variables.

**Depends on**: P2-01 through P2-05

---

## Context

**Background**: Each Phase 2 task spec includes its own test requirements. This task is the integration pass — ensuring the full test suite is coherent, CI is green with the new env vars, and there are no coverage gaps at the integration level (cross-feature scenarios that individual task tests may miss).

**Affected components**:
- [x] All test files
- [x] `tests/conftest.py` (new fixtures for auth, storage)
- [x] `.github/workflows/ci.yml` (new env vars)
- [x] `Makefile` (no changes expected)

---

## Requirements

**Functional**:

The following integration scenarios must have tests (individual unit tests are covered in each P2-X task):

1. **End-to-end upload as authenticated tenant**: upload → ingest → verify chunks stored under correct `account_id`
2. **End-to-end query as authenticated tenant**: upload doc, query it, get grounded answer
3. **Tenant isolation on query**: upload doc as tenant A, query as tenant B, confirm no results/different answer
4. **MCP tool flow**: upload via `upload_document` tool, query via `query_documents`, delete via `delete_document`, confirm gone via `list_documents`
5. **Storage backend switching**: verify that with `STORAGE_BACKEND=s3` (moto mock), upload and delete work end-to-end

**Non-functional**:
- All tests run with `make test` — no manual steps
- No real OpenAI API calls (mock as per Phase 1 patterns)
- No real AWS calls (use `moto` for S3 tests)
- CI must pass with the additions

---

## conftest.py Updates

Add the following shared fixtures:

```python
# tests/conftest.py additions

import jwt
import pytest
from moto import mock_aws
import boto3

TEST_JWT_SECRET = "test-secret-do-not-use-in-prod"
TEST_ACCOUNT_A = "acct_test_a"
TEST_ACCOUNT_B = "acct_test_b"

@pytest.fixture(autouse=True)
def set_jwt_secret(monkeypatch):
    """Ensure all tests use the test JWT secret."""
    monkeypatch.setattr("app.config.settings.jwt_secret", TEST_JWT_SECRET)

@pytest.fixture
def token_a() -> str:
    return jwt.encode({"sub": TEST_ACCOUNT_A}, TEST_JWT_SECRET, algorithm="HS256")

@pytest.fixture
def token_b() -> str:
    return jwt.encode({"sub": TEST_ACCOUNT_B}, TEST_JWT_SECRET, algorithm="HS256")

@pytest.fixture
def auth_headers_a(token_a: str) -> dict:
    return {"Authorization": f"Bearer {token_a}"}

@pytest.fixture
def auth_headers_b(token_b: str) -> dict:
    return {"Authorization": f"Bearer {token_b}"}

@pytest.fixture
def mock_s3():
    """Mocked S3 environment using moto."""
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="test-rag-bucket")
        yield client

@pytest.fixture
def s3_storage_settings(monkeypatch, mock_s3):
    """Override config to use S3 backend with moto."""
    monkeypatch.setattr("app.config.settings.storage_backend", "s3")
    monkeypatch.setattr("app.config.settings.s3_bucket", "test-rag-bucket")
    monkeypatch.setattr("app.config.settings.s3_region", "us-east-1")
```

---

## Integration Tests to Write

Create `tests/test_integration.py`:

```python
# tests/test_integration.py

class TestEndToEndUploadAndQuery:
    def test_upload_and_query_returns_grounded_answer(
        self, client, auth_headers_a, mock_openai
    ):
        """Full flow: upload doc → query → get answer with citations."""
        # Upload
        resp = client.post("/documents", headers=auth_headers_a, files={"file": ("test.txt", b"...")})
        assert resp.status_code == 201
        doc_id = resp.json()["document_id"]

        # Query
        resp = client.post("/query", headers=auth_headers_a,
                           json={"question": "What is in the document?"})
        assert resp.status_code == 200
        assert "answer" in resp.json()
        assert len(resp.json()["citations"]) > 0

    def test_tenant_isolation(self, client, auth_headers_a, auth_headers_b, mock_openai):
        """Account B cannot retrieve Account A's document chunks."""
        # Upload as A
        client.post("/documents", headers=auth_headers_a,
                    files={"file": ("secret.txt", b"Secret content for A only")})

        # Query as B — should get no relevant chunks, answer reflects no info found
        resp = client.post("/query", headers=auth_headers_b,
                           json={"question": "What is the secret content?"})
        assert resp.status_code == 200
        # The LLM answer should not contain A's content (mock LLM returns based on context)
        # At minimum, assert no citations from A's document appear
        for citation in resp.json().get("citations", []):
            assert citation["document_id"] != "<a_doc_id>"


class TestDocumentLifecycle:
    def test_upload_list_delete_flow(self, client, auth_headers_a):
        # Upload
        resp = client.post("/documents", headers=auth_headers_a,
                           files={"file": ("report.txt", b"Report content")})
        doc_id = resp.json()["document_id"]

        # List — should appear
        resp = client.get("/documents", headers=auth_headers_a)
        ids = [d["document_id"] for d in resp.json()["documents"]]
        assert doc_id in ids

        # Delete
        resp = client.delete(f"/documents/{doc_id}", headers=auth_headers_a)
        assert resp.status_code == 204

        # List — should be gone
        resp = client.get("/documents", headers=auth_headers_a)
        ids = [d["document_id"] for d in resp.json()["documents"]]
        assert doc_id not in ids


class TestS3StorageBackend:
    def test_upload_with_s3_backend(
        self, client, auth_headers_a, s3_storage_settings, mock_openai
    ):
        resp = client.post("/documents", headers=auth_headers_a,
                           files={"file": ("s3test.txt", b"S3 content")})
        assert resp.status_code == 201
        # Verify object exists in moto S3
        import boto3
        s3 = boto3.client("s3", region_name="us-east-1")
        objects = s3.list_objects_v2(Bucket="test-rag-bucket", Prefix="acct_test_a/")
        assert objects["KeyCount"] == 1

    def test_delete_with_s3_backend(
        self, client, auth_headers_a, s3_storage_settings, mock_openai
    ):
        resp = client.post("/documents", headers=auth_headers_a,
                           files={"file": ("s3del.txt", b"Delete me")})
        doc_id = resp.json()["document_id"]
        client.delete(f"/documents/{doc_id}", headers=auth_headers_a)

        import boto3
        s3 = boto3.client("s3", region_name="us-east-1")
        objects = s3.list_objects_v2(Bucket="test-rag-bucket", Prefix="acct_test_a/")
        assert objects["KeyCount"] == 0
```

---

## CI Updates

Update `.github/workflows/ci.yml` to include new env vars in the test job:

```yaml
# .github/workflows/ci.yml — test job env section additions
env:
  DATABASE_URL: postgresql://rag:rag@localhost:5432/rag
  OPENAI_API_KEY: sk-test-not-real
  JWT_SECRET: ci-test-secret-not-for-production
  STORAGE_BACKEND: local
  # S3 vars not needed — moto mocks them; set to dummy values to avoid config errors
  S3_BUCKET: ci-test-bucket
  S3_REGION: us-east-1
  AWS_ACCESS_KEY_ID: test
  AWS_SECRET_ACCESS_KEY: test
```

---

## Test Requirements Summary

By the end of P2-06, `make test` must cover:

| Area | Tests |
|---|---|
| Auth service | unit tests in `test_auth.py` (from P2-02) |
| Storage — local | unit tests in `test_storage.py` (from P2-03) |
| Storage — S3 | unit tests in `test_storage.py` (from P2-03) |
| Document management | unit tests in `test_document_management.py` (from P2-04) |
| MCP tools | unit tests in `test_mcp_server.py` (from P2-05) |
| End-to-end upload + query | `test_integration.py` (this task) |
| Tenant isolation | `test_integration.py` (this task) |
| Document lifecycle | `test_integration.py` (this task) |
| S3 backend end-to-end | `test_integration.py` (this task) |

---

## Acceptance Criteria

- [ ] `make test` passes with zero failures
- [ ] No real external API calls in any test (OpenAI mocked, S3 mocked via moto)
- [ ] Tenant isolation is tested at the integration level
- [ ] S3 backend is tested via moto (no real AWS credentials needed)
- [ ] CI workflow passes with the new env vars
- [ ] `make lint && make typecheck` passes

---

## Validation Steps

```bash
# Run full suite
make test

# Run with coverage (optional, useful to see gaps)
uv run pytest --cov=app --cov-report=term-missing

# CI simulation
act -j test  # if act (GitHub Actions local runner) is installed
```

---

## Risks

- `moto` and `boto3` must be in the same version compatibility band — check PyPI for the current recommended pair
- The `autouse=True` fixture for `jwt_secret` will affect all tests including Phase 1 tests. If Phase 1 tests don't set an `Authorization` header and the routes now require auth, those tests will start returning 401. Fix by adding `auth_headers_a` to any test that hits auth-protected endpoints.
- Integration tests are inherently slower than unit tests. Consider marking them with `@pytest.mark.integration` and allowing CI to optionally skip them on draft PRs.

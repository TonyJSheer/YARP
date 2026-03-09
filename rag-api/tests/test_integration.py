"""Integration tests — cross-feature Phase 2 scenarios.

Covers:
- End-to-end upload → query flow
- Tenant isolation at the DB retrieval level
- Full document lifecycle (upload → list → delete → confirm gone)
- S3 storage backend (via moto)
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import boto3
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from tests.conftest import TEST_ACCOUNT_A

FAKE_VECTOR = [0.1] * 768


# ---------------------------------------------------------------------------
# Module-level autouse fixture — mock the ingest pipeline for all tests here
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def mock_ingest_pipeline() -> pytest.FixtureRequest:
    """Mock embed_chunks and extract_text so uploads work without real models or S3 reads."""
    with (
        patch(
            "app.services.embedding.embed_chunks",
            side_effect=lambda texts: [FAKE_VECTOR for _ in texts],
        ),
        patch(
            "app.services.chunking.extract_text",
            return_value=(["Integration test document content."], [None]),
        ),
    ):
        yield


@pytest.fixture
def mock_openai() -> pytest.FixtureRequest:
    """Mock query-time LLM calls: embed_query and generate_answer."""
    with (
        patch("app.services.embedding.embed_query", return_value=FAKE_VECTOR),
        patch(
            "app.services.generation.generate_answer",
            side_effect=lambda question, chunks, **kwargs: ("Mocked answer.", chunks),
        ),
    ):
        yield


# ---------------------------------------------------------------------------
# End-to-end upload + query
# ---------------------------------------------------------------------------


class TestEndToEndUploadAndQuery:
    def test_upload_and_query_returns_grounded_answer(
        self,
        client: TestClient,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        auth_headers_a: dict[str, str],
        mock_openai: None,
    ) -> None:
        """Full flow: upload doc → query → get answer with citations."""
        monkeypatch.setattr(settings, "upload_dir", str(tmp_path))

        resp = client.post(
            "/documents",
            headers=auth_headers_a,
            files={"file": ("test.txt", b"Integration test content.", "text/plain")},
        )
        assert resp.status_code == 201

        resp = client.post(
            "/query",
            headers=auth_headers_a,
            json={"question": "What is in the document?"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "answer" in body
        assert len(body["citations"]) > 0

    def test_tenant_isolation(
        self,
        client: TestClient,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        auth_headers_a: dict[str, str],
        auth_headers_b: dict[str, str],
        mock_openai: None,
    ) -> None:
        """Account B cannot retrieve Account A's document chunks via the query endpoint."""
        monkeypatch.setattr(settings, "upload_dir", str(tmp_path))

        # Upload as A
        resp = client.post(
            "/documents",
            headers=auth_headers_a,
            files={"file": ("secret.txt", b"Secret content for A only", "text/plain")},
        )
        assert resp.status_code == 201

        # Query as B — retrieve filters by account_id so B gets no chunks
        resp = client.post(
            "/query",
            headers=auth_headers_b,
            json={"question": "What is the secret content?"},
        )
        assert resp.status_code == 200
        assert resp.json().get("citations", []) == []


# ---------------------------------------------------------------------------
# Document lifecycle
# ---------------------------------------------------------------------------


class TestDocumentLifecycle:
    def test_upload_list_delete_flow(
        self,
        client: TestClient,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        auth_headers_a: dict[str, str],
    ) -> None:
        monkeypatch.setattr(settings, "upload_dir", str(tmp_path))

        # Upload
        resp = client.post(
            "/documents",
            headers=auth_headers_a,
            files={"file": ("report.txt", b"Report content", "text/plain")},
        )
        assert resp.status_code == 201
        doc_id = resp.json()["document_id"]

        # List — should appear
        resp = client.get("/documents", headers=auth_headers_a)
        assert resp.status_code == 200
        ids = [d["document_id"] for d in resp.json()["documents"]]
        assert doc_id in ids

        # Delete
        resp = client.delete(f"/documents/{doc_id}", headers=auth_headers_a)
        assert resp.status_code == 204

        # List — should be gone
        resp = client.get("/documents", headers=auth_headers_a)
        ids = [d["document_id"] for d in resp.json()["documents"]]
        assert doc_id not in ids


# ---------------------------------------------------------------------------
# S3 storage backend (moto)
# ---------------------------------------------------------------------------


class TestS3StorageBackend:
    def test_upload_with_s3_backend(
        self,
        client: TestClient,
        auth_headers_a: dict[str, str],
        s3_storage_settings: None,
        mock_openai: None,
    ) -> None:
        """Upload stores the file in S3 (moto) under the correct account prefix."""
        resp = client.post(
            "/documents",
            headers=auth_headers_a,
            files={"file": ("s3test.txt", b"S3 content", "text/plain")},
        )
        assert resp.status_code == 201

        s3 = boto3.client("s3", region_name="us-east-1")
        objects = s3.list_objects_v2(Bucket="test-rag-bucket", Prefix=f"{TEST_ACCOUNT_A}/")
        assert objects["KeyCount"] == 1

    def test_delete_with_s3_backend(
        self,
        client: TestClient,
        auth_headers_a: dict[str, str],
        s3_storage_settings: None,
        mock_openai: None,
    ) -> None:
        """Delete removes the file from S3 (moto)."""
        resp = client.post(
            "/documents",
            headers=auth_headers_a,
            files={"file": ("s3del.txt", b"Delete me", "text/plain")},
        )
        assert resp.status_code == 201
        doc_id = resp.json()["document_id"]

        resp = client.delete(f"/documents/{doc_id}", headers=auth_headers_a)
        assert resp.status_code == 204

        s3 = boto3.client("s3", region_name="us-east-1")
        objects = s3.list_objects_v2(Bucket="test-rag-bucket", Prefix=f"{TEST_ACCOUNT_A}/")
        assert objects["KeyCount"] == 0

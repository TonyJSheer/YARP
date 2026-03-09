import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import SessionLocal
from app.models.chunk import Chunk
from app.models.document import Document
from app.services import ingestion

FAKE_VECTOR = [0.1] * 768


@pytest.fixture(autouse=True)
def mock_embed_chunks() -> pytest.FixtureRequest:
    """Patch embed_chunks in all tests to avoid real embedding calls."""
    with patch(
        "app.services.embedding.embed_chunks",
        side_effect=lambda texts: [FAKE_VECTOR for _ in texts],
    ):
        yield


# ---------------------------------------------------------------------------
# Upload endpoint tests (POST /documents)
# ---------------------------------------------------------------------------


def test_upload_txt_returns_201(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    auth_headers: dict[str, str],
) -> None:
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))

    response = client.post(
        "/documents",
        files={"file": ("hello.txt", b"Hello, world! This is a test document.", "text/plain")},
        headers=auth_headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "processing"
    uuid.UUID(body["document_id"])  # raises ValueError if not a valid UUID


def test_upload_saves_file_to_disk(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    auth_headers: dict[str, str],
) -> None:
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    content = b"File content to verify on disk"

    client.post(
        "/documents",
        files={"file": ("disk_test.txt", content, "text/plain")},
        headers=auth_headers,
    )

    # Files are now scoped by account_id — find the saved file recursively
    saved_files = list(tmp_path.rglob("*"))
    saved_files = [f for f in saved_files if f.is_file()]
    assert len(saved_files) == 1
    assert saved_files[0].read_bytes() == content


def test_upload_creates_db_record(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    auth_headers: dict[str, str],
) -> None:
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))

    response = client.post(
        "/documents",
        files={"file": ("record_test.txt", b"DB record content", "text/plain")},
        headers=auth_headers,
    )
    doc_id = uuid.UUID(response.json()["document_id"])

    with SessionLocal() as session:
        doc = session.get(Document, doc_id)
        assert doc is not None
        assert doc.filename == "record_test.txt"
        assert doc.status == "processing"
        assert len(doc.sha256) == 64  # sha256 hex is always 64 chars
        assert doc.account_id == "test-account"


def test_upload_unsupported_type_returns_400(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    auth_headers: dict[str, str],
) -> None:
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))

    response = client.post(
        "/documents",
        files={"file": ("payload.exe", b"not a document", "application/octet-stream")},
        headers=auth_headers,
    )

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "unsupported_file_type"
    assert error["field"] == "file"


def test_upload_md_file_accepted(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    auth_headers: dict[str, str],
) -> None:
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))

    response = client.post(
        "/documents",
        files={"file": ("notes.md", b"# Heading\n\nSome markdown content.", "text/markdown")},
        headers=auth_headers,
    )

    assert response.status_code == 201
    assert response.json()["status"] == "processing"


def test_upload_pdf_file_accepted(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    auth_headers: dict[str, str],
) -> None:
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))

    # Minimal valid PDF with text content
    minimal_pdf = b"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]
  /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj
4 0 obj << /Length 44 >>
stream
BT /F1 12 Tf 100 700 Td (Hello PDF) Tj ET
endstream
endobj
5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj
xref
0 6
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000266 00000 n
0000000360 00000 n
trailer << /Size 6 /Root 1 0 R >>
startxref
441
%%EOF
"""
    response = client.post(
        "/documents",
        files={"file": ("doc.pdf", minimal_pdf, "application/pdf")},
        headers=auth_headers,
    )

    assert response.status_code == 201
    assert response.json()["status"] == "processing"


# ---------------------------------------------------------------------------
# Worker / run_ingest_job tests
# ---------------------------------------------------------------------------


def test_worker_processes_job(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run_ingest_job should complete ingestion and set status='ready'."""
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))

    content = b"This is a sentence. And another sentence here. One more for good measure."
    account_dir = tmp_path / "worker-test-account"
    account_dir.mkdir(parents=True, exist_ok=True)
    file_path = account_dir / "test.txt"
    file_path.write_bytes(content)

    with SessionLocal() as db:
        doc = Document(
            account_id="worker-test-account",
            filename="test.txt",
            content_type="text/plain",
            sha256="abc123",
            storage_key=str(file_path),
            status="processing",
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        doc_id = doc.id

        ingestion.run_ingest_job(str(doc_id), db)

    with SessionLocal() as db:
        doc_after = db.get(Document, doc_id)
        assert doc_after is not None
        assert doc_after.status == "ready"
        assert doc_after.error_message is None
        chunks = db.query(Chunk).filter(Chunk.document_id == doc_id).all()
        assert len(chunks) >= 1
        assert all(c.embedding is not None for c in chunks)


def test_worker_marks_failed_on_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run_ingest_job should set status='failed' and populate error_message on exception."""
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))

    with SessionLocal() as db:
        doc = Document(
            account_id="worker-fail-account",
            filename="fail.txt",
            content_type="text/plain",
            sha256="deadbeef",
            storage_key="/nonexistent/path/fail.txt",
            status="processing",
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        doc_id = doc.id

        with pytest.raises(Exception):
            ingestion.run_ingest_job(str(doc_id), db)

    with SessionLocal() as db:
        doc_after = db.get(Document, doc_id)
        assert doc_after is not None
        assert doc_after.status == "failed"
        assert doc_after.error_message is not None
        assert len(doc_after.error_message) > 0


def test_upload_creates_chunk_rows_after_job(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    auth_headers: dict[str, str],
) -> None:
    """Chunks exist after run_ingest_job completes (not immediately after upload)."""
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    content = b"This is a sentence. And another sentence here. One more for good measure."

    response = client.post(
        "/documents",
        files={"file": ("chunks_test.txt", content, "text/plain")},
        headers=auth_headers,
    )
    assert response.status_code == 201
    doc_id_str = response.json()["document_id"]

    # Simulate the worker running the job
    with SessionLocal() as db:
        ingestion.run_ingest_job(doc_id_str, db)

    with SessionLocal() as session:
        doc_id = uuid.UUID(doc_id_str)
        chunks = session.query(Chunk).filter(Chunk.document_id == doc_id).all()
        assert len(chunks) >= 1
        assert all(c.text.strip() for c in chunks)


def test_upload_chunks_have_embeddings_after_job(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    auth_headers: dict[str, str],
) -> None:
    """Embeddings exist after run_ingest_job completes."""
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))

    response = client.post(
        "/documents",
        files={"file": ("embed_test.txt", b"Embedding test sentence.", "text/plain")},
        headers=auth_headers,
    )
    assert response.status_code == 201
    doc_id_str = response.json()["document_id"]

    with SessionLocal() as db:
        ingestion.run_ingest_job(doc_id_str, db)

    with SessionLocal() as session:
        doc_id = uuid.UUID(doc_id_str)
        chunks = session.query(Chunk).filter(Chunk.document_id == doc_id).all()
        assert len(chunks) >= 1
        assert all(c.embedding is not None for c in chunks)


# ---------------------------------------------------------------------------
# GET /documents/{id} tests
# ---------------------------------------------------------------------------


def test_get_document_returns_detail(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    auth_headers: dict[str, str],
) -> None:
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))

    upload_resp = client.post(
        "/documents",
        files={"file": ("status_test.txt", b"Status check content.", "text/plain")},
        headers=auth_headers,
    )
    assert upload_resp.status_code == 201
    doc_id = upload_resp.json()["document_id"]

    resp = client.get(f"/documents/{doc_id}", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["document_id"] == doc_id
    assert body["status"] == "processing"
    assert "filename" in body
    assert "chunk_count" in body
    assert "error_message" in body


def test_get_document_not_found(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    resp = client.get(f"/documents/{uuid.uuid4()}", headers=auth_headers)
    assert resp.status_code == 404


def test_get_document_wrong_account(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    auth_headers_a: dict[str, str],
    auth_headers_b: dict[str, str],
) -> None:
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))

    upload_resp = client.post(
        "/documents",
        files={"file": ("acl_test.txt", b"Account isolation test.", "text/plain")},
        headers=auth_headers_a,
    )
    assert upload_resp.status_code == 201
    doc_id = upload_resp.json()["document_id"]

    # Account B cannot see account A's document
    resp = client.get(f"/documents/{doc_id}", headers=auth_headers_b)
    assert resp.status_code == 404

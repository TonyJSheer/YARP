import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import SessionLocal
from app.models.chunk import Chunk
from app.models.document import Document

FAKE_VECTOR = [0.1] * 768


@pytest.fixture(autouse=True)
def mock_embed_chunks() -> pytest.FixtureRequest:
    """Patch embed_chunks in all tests to avoid real OpenAI calls."""
    with patch(
        "app.services.embedding.embed_chunks",
        side_effect=lambda texts: [FAKE_VECTOR for _ in texts],
    ):
        yield


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
    assert body["status"] == "ready"
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
        assert doc.status == "ready"
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


def test_upload_creates_chunk_rows(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    auth_headers: dict[str, str],
) -> None:
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    content = b"This is a sentence. And another sentence here. One more for good measure."

    response = client.post(
        "/documents",
        files={"file": ("chunks_test.txt", content, "text/plain")},
        headers=auth_headers,
    )
    assert response.status_code == 201
    doc_id = uuid.UUID(response.json()["document_id"])

    with SessionLocal() as session:
        chunks = session.query(Chunk).filter(Chunk.document_id == doc_id).all()
        assert len(chunks) >= 1
        assert all(c.text.strip() for c in chunks)


def test_upload_chunks_have_embeddings(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    auth_headers: dict[str, str],
) -> None:
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))

    response = client.post(
        "/documents",
        files={"file": ("embed_test.txt", b"Embedding test sentence.", "text/plain")},
        headers=auth_headers,
    )
    assert response.status_code == 201
    doc_id = uuid.UUID(response.json()["document_id"])

    with SessionLocal() as session:
        chunks = session.query(Chunk).filter(Chunk.document_id == doc_id).all()
        assert len(chunks) >= 1
        assert all(c.embedding is not None for c in chunks)


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
    assert response.json()["status"] == "ready"


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
    assert response.json()["status"] == "ready"

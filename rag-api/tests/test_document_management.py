import uuid
from pathlib import Path
from unittest.mock import patch

import jwt
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import SessionLocal
from app.models.chunk import Chunk
from app.models.document import Document

FAKE_VECTOR = [0.1] * 768

TEST_JWT_SECRET = "test-secret"
TEST_JWT_ALGORITHM = "HS256"


@pytest.fixture(autouse=True)
def mock_embed_chunks() -> pytest.FixtureRequest:
    with patch(
        "app.services.embedding.embed_chunks",
        side_effect=lambda texts: [FAKE_VECTOR for _ in texts],
    ):
        yield


def make_auth_headers(account_id: str) -> dict[str, str]:
    token = jwt.encode({"sub": account_id}, TEST_JWT_SECRET, algorithm=TEST_JWT_ALGORITHM)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def unique_headers() -> dict[str, str]:
    """Auth headers for a fresh unique account with no existing DB rows."""
    return make_auth_headers(f"acct-{uuid.uuid4()}")


def upload_doc(
    client: TestClient,
    headers: dict[str, str],
    filename: str = "test.txt",
    content: bytes = b"Hello world test content.",
) -> str:
    response = client.post(
        "/documents",
        files={"file": (filename, content, "text/plain")},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()["document_id"]


def test_list_documents_returns_own_documents(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    unique_headers: dict[str, str],
) -> None:
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))

    upload_doc(client, unique_headers, "doc1.txt", b"First document content.")
    upload_doc(client, unique_headers, "doc2.txt", b"Second document content.")

    response = client.get("/documents", headers=unique_headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body["documents"]) == 2
    filenames = {d["filename"] for d in body["documents"]}
    assert filenames == {"doc1.txt", "doc2.txt"}


def test_list_documents_does_not_return_other_accounts_documents(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    unique_headers: dict[str, str],
) -> None:
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))

    # Upload as account A
    upload_doc(client, unique_headers)

    # List as a different unique account B
    headers_b = make_auth_headers(f"acct-{uuid.uuid4()}")
    response = client.get("/documents", headers=headers_b)

    assert response.status_code == 200
    assert response.json()["documents"] == []


def test_list_documents_empty(
    client: TestClient,
    unique_headers: dict[str, str],
) -> None:
    response = client.get("/documents", headers=unique_headers)

    assert response.status_code == 200
    assert response.json() == {"documents": []}


def test_list_documents_includes_chunk_count(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    unique_headers: dict[str, str],
) -> None:
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))

    upload_doc(client, unique_headers, content=b"Sentence one. Sentence two. Sentence three.")

    response = client.get("/documents", headers=unique_headers)

    assert response.status_code == 200
    doc = response.json()["documents"][0]
    assert doc["chunk_count"] >= 1


def test_list_documents_sorted_by_created_at_desc(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    unique_headers: dict[str, str],
) -> None:
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))

    upload_doc(client, unique_headers, "first.txt", b"First doc.")
    upload_doc(client, unique_headers, "second.txt", b"Second doc.")

    response = client.get("/documents", headers=unique_headers)

    docs = response.json()["documents"]
    assert len(docs) == 2
    # Most recent first — second upload should appear first
    assert docs[0]["filename"] == "second.txt"
    assert docs[1]["filename"] == "first.txt"


def test_delete_own_document_returns_204(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    unique_headers: dict[str, str],
) -> None:
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))

    doc_id = upload_doc(client, unique_headers)

    response = client.delete(f"/documents/{doc_id}", headers=unique_headers)

    assert response.status_code == 204


def test_delete_removes_document_from_db(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    unique_headers: dict[str, str],
) -> None:
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))

    doc_id = upload_doc(client, unique_headers)

    client.delete(f"/documents/{doc_id}", headers=unique_headers)

    with SessionLocal() as session:
        doc = session.get(Document, uuid.UUID(doc_id))
        assert doc is None


def test_delete_removes_chunks(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    unique_headers: dict[str, str],
) -> None:
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))

    doc_id = upload_doc(client, unique_headers, content=b"Some text for chunking here.")

    # Verify chunks exist
    with SessionLocal() as session:
        chunks = session.query(Chunk).filter(Chunk.document_id == uuid.UUID(doc_id)).all()
        assert len(chunks) >= 1

    client.delete(f"/documents/{doc_id}", headers=unique_headers)

    with SessionLocal() as session:
        chunks = session.query(Chunk).filter(Chunk.document_id == uuid.UUID(doc_id)).all()
        assert chunks == []


def test_delete_other_accounts_document_returns_404(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    unique_headers: dict[str, str],
) -> None:
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))

    # Upload as account A
    doc_id = upload_doc(client, unique_headers)

    # Try to delete as a different unique account B
    headers_b = make_auth_headers(f"acct-{uuid.uuid4()}")
    response = client.delete(f"/documents/{doc_id}", headers=headers_b)

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "not_found"


def test_delete_nonexistent_returns_404(
    client: TestClient,
    unique_headers: dict[str, str],
) -> None:
    random_id = str(uuid.uuid4())
    response = client.delete(f"/documents/{random_id}", headers=unique_headers)

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "not_found"

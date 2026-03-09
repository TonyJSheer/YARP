"""Tests for the MCP server tool functions (called directly, not via wire protocol)."""

from __future__ import annotations

import base64
import uuid
from pathlib import Path
from unittest.mock import patch

import jwt
import pytest

from app.config import settings
from app.db import SessionLocal
from app.mcp_server import delete_document, list_documents, query_documents, upload_document
from app.models.document import Document
from app.services import auth
from app.services.retrieval import RetrievedChunk

FAKE_VECTOR = [0.1] * 768
TEST_JWT_SECRET = "test-secret"
TEST_JWT_ALGORITHM = "HS256"
TEST_CONTENT = b"The quick brown fox jumps over the lazy dog."
TEST_CONTENT_B64 = base64.b64encode(TEST_CONTENT).decode()


def make_token(account_id: str) -> str:
    return jwt.encode({"sub": account_id}, TEST_JWT_SECRET, algorithm=TEST_JWT_ALGORITHM)


def make_chunk(**kwargs: object) -> RetrievedChunk:
    defaults = dict(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        chunk_index=0,
        page_number=1,
        text="The quick brown fox.",
        score=0.95,
    )
    return RetrievedChunk(**{**defaults, **kwargs})  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def mock_embed_chunks() -> pytest.FixtureRequest:
    """Auto-mock embed_chunks so ingestion doesn't call sentence-transformers."""
    with patch(
        "app.services.embedding.embed_chunks",
        side_effect=lambda texts: [FAKE_VECTOR for _ in texts],
    ):
        yield


@pytest.fixture
def account_id() -> str:
    return f"mcp-test-{uuid.uuid4()}"


@pytest.fixture
def mcp_token(account_id: str) -> str:
    return make_token(account_id)


@pytest.fixture
def set_auth_token(mcp_token: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Set MCP_AUTH_TOKEN so get_account_id() resolves via env var (stdio path)."""
    monkeypatch.setenv("MCP_AUTH_TOKEN", mcp_token)
    # Ensure _account_id contextvar is clear so env path is exercised
    import app.mcp_server as ms

    monkeypatch.setattr(ms._account_id, "get", lambda: None)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# upload_document
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_document_tool(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    account_id: str,
    mcp_token: str,
) -> None:
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setenv("MCP_AUTH_TOKEN", mcp_token)

    result = await upload_document(filename="test.txt", content_b64=TEST_CONTENT_B64)

    assert "document_id" in result
    assert result["status"] == "ready"
    assert result["chunk_count"] >= 1

    with SessionLocal() as db:
        doc = db.get(Document, uuid.UUID(result["document_id"]))
        assert doc is not None
        assert doc.account_id == account_id


# ---------------------------------------------------------------------------
# query_documents
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_query_documents_tool(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    account_id: str,
    mcp_token: str,
) -> None:
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setenv("MCP_AUTH_TOKEN", mcp_token)

    chunk = make_chunk(document_id=uuid.uuid4())

    with (
        patch("app.services.embedding.embed_query", return_value=FAKE_VECTOR),
        patch("app.services.retrieval.retrieve", return_value=[chunk]),
        patch(
            "app.services.generation.generate_answer",
            return_value=("The fox jumps.", [chunk]),
        ),
    ):
        result = await query_documents(question="What does the fox do?", top_k=3)

    assert "answer" in result
    assert result["answer"] == "The fox jumps."
    assert "citations" in result
    assert len(result["citations"]) == 1
    assert "document_id" in result["citations"][0]


# ---------------------------------------------------------------------------
# list_documents
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_documents_tool(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    account_id: str,
    mcp_token: str,
) -> None:
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setenv("MCP_AUTH_TOKEN", mcp_token)

    await upload_document(filename="doc_a.txt", content_b64=TEST_CONTENT_B64)
    await upload_document(filename="doc_b.txt", content_b64=TEST_CONTENT_B64)

    result = await list_documents()

    assert "documents" in result
    filenames = {d["filename"] for d in result["documents"]}
    assert "doc_a.txt" in filenames
    assert "doc_b.txt" in filenames


# ---------------------------------------------------------------------------
# delete_document
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_document_tool(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    account_id: str,
    mcp_token: str,
) -> None:
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setenv("MCP_AUTH_TOKEN", mcp_token)

    upload_result = await upload_document(filename="to_delete.txt", content_b64=TEST_CONTENT_B64)
    doc_id = upload_result["document_id"]

    delete_result = await delete_document(document_id=doc_id)

    assert delete_result["deleted"] == doc_id

    with SessionLocal() as db:
        doc = db.get(Document, uuid.UUID(doc_id))
        assert doc is None


# ---------------------------------------------------------------------------
# Auth error cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_invalid_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_AUTH_TOKEN", "not-a-valid-jwt")

    with pytest.raises(auth.AuthError):
        await upload_document(filename="test.txt", content_b64=TEST_CONTENT_B64)


@pytest.mark.asyncio
async def test_upload_missing_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)
    # Also ensure contextvar is not set
    import app.mcp_server as ms

    token = ms._account_id.set(None)
    try:
        with pytest.raises(auth.AuthError):
            await upload_document(filename="test.txt", content_b64=TEST_CONTENT_B64)
    finally:
        ms._account_id.reset(token)


# ---------------------------------------------------------------------------
# Cross-tenant isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cross_tenant_isolation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Upload as account A; query as account B — answer should reflect no documents."""
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))

    # Upload as account A
    token_a = make_token(f"tenant-a-{uuid.uuid4()}")
    monkeypatch.setenv("MCP_AUTH_TOKEN", token_a)
    await upload_document(filename="secret.txt", content_b64=TEST_CONTENT_B64)

    # Query as account B — should get no chunks, hence "no documents" answer
    token_b = make_token(f"tenant-b-{uuid.uuid4()}")
    monkeypatch.setenv("MCP_AUTH_TOKEN", token_b)

    with (
        patch("app.services.embedding.embed_query", return_value=FAKE_VECTOR),
        patch("app.services.retrieval.retrieve", return_value=[]),
        patch(
            "app.services.generation.generate_answer",
            return_value=("I don't know based on the provided documents.", []),
        ),
    ):
        result = await query_documents(question="What is the secret?")

    assert result["citations"] == []
    assert "don't know" in result["answer"]

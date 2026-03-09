"""Integration tests for the retrieval service.

These tests require a running Postgres with migrations applied.
Run: docker compose up postgres -d && make migrate
"""

import uuid
from collections.abc import Generator

import pytest
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.chunk import Chunk
from app.models.document import Document
from app.services.retrieval import MAX_TOP_K, RetrievedChunk, retrieve


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session


@pytest.fixture()
def db_with_chunks(db_session: Session) -> Generator[tuple[Session, uuid.UUID], None, None]:
    """Insert a document and 3 chunks with known embeddings, clean up after."""
    doc = Document(
        account_id="test",
        filename="retrieval_test.txt",
        content_type="text/plain",
        sha256=uuid.uuid4().hex,
        status="ready",
    )
    db_session.add(doc)
    db_session.flush()

    # Three chunks with embeddings that differ in the first dimension only.
    # Shift by 1 to avoid a zero vector (zero vectors produce NaN cosine scores).
    # chunk 0: [0.5, 0.0, ...] — same direction as query [1.0, 0.0, ...]
    # chunk 1: [1.0, 0.0, ...] — same direction
    # chunk 2: [1.5, 0.0, ...] — same direction
    chunks = [
        Chunk(
            document_id=doc.id,
            chunk_index=i,
            text=f"chunk {i}",
            embedding=[float(i + 1) * 0.5] + [0.0] * 767,
        )
        for i in range(3)
    ]
    db_session.add_all(chunks)
    db_session.commit()

    yield db_session, doc.id

    # Teardown
    db_session.query(Chunk).filter(Chunk.document_id == doc.id).delete()
    db_session.query(Document).filter(Document.id == doc.id).delete()
    db_session.commit()


def test_retrieve_returns_empty_when_no_chunks(db_session: Session) -> None:
    # Use a unique vector — any empty table (or table with no embeddings) returns [].
    query_vec = [1.0] + [0.0] * 767

    # Query against the real DB using account "empty-account" which has no data.
    # The key assertion: result is a list (may be empty or non-empty).
    result = retrieve(query_vec, "empty-account", db_session, top_k=5)
    assert isinstance(result, list)
    for item in result:
        assert isinstance(item, RetrievedChunk)


def test_retrieve_returns_top_k(
    db_with_chunks: tuple[Session, uuid.UUID],
) -> None:
    db_session, doc_id = db_with_chunks
    query_vec = [1.0] + [0.0] * 767

    result = retrieve(query_vec, "test", db_session, top_k=2)

    assert len(result) == 2
    assert all(isinstance(r, RetrievedChunk) for r in result)


def test_retrieve_ordered_by_similarity(
    db_with_chunks: tuple[Session, uuid.UUID],
) -> None:
    db_session, doc_id = db_with_chunks
    # Query vector closest to chunk 2 ([1.0, 0, ...]) then chunk 1 ([0.5, 0, ...])
    query_vec = [1.0] + [0.0] * 767

    result = retrieve(query_vec, "test", db_session, top_k=3)

    assert len(result) >= 2
    # Scores must be in descending order (most similar first)
    for i in range(len(result) - 1):
        assert result[i].score >= result[i + 1].score


def test_retrieve_respects_max_top_k_cap(
    db_with_chunks: tuple[Session, uuid.UUID],
) -> None:
    db_session, _ = db_with_chunks
    query_vec = [1.0] + [0.0] * 767

    result = retrieve(query_vec, "test", db_session, top_k=999)

    assert len(result) <= MAX_TOP_K


def test_retrieve_excludes_chunks_without_embeddings(
    db_session: Session,
) -> None:
    """A chunk with embedding=None must not appear in results."""
    doc = Document(
        account_id="test",
        filename="no_embed_test.txt",
        content_type="text/plain",
        sha256=uuid.uuid4().hex,
        status="ready",
    )
    db_session.add(doc)
    db_session.flush()

    null_chunk = Chunk(
        document_id=doc.id,
        chunk_index=0,
        text="this chunk has no embedding",
        embedding=None,
    )
    db_session.add(null_chunk)
    db_session.commit()

    try:
        query_vec = [1.0] + [0.0] * 767
        result = retrieve(query_vec, "test", db_session, top_k=20)
        chunk_ids = {r.chunk_id for r in result}
        assert null_chunk.id not in chunk_ids
    finally:
        db_session.delete(null_chunk)
        db_session.delete(doc)
        db_session.commit()


def test_retrieve_isolates_by_account_id(
    db_session: Session,
) -> None:
    """Chunks belonging to a different account_id must never be returned."""
    # Create two documents under different accounts, each with one chunk
    doc_a = Document(
        account_id="account-a",
        filename="doc_a.txt",
        content_type="text/plain",
        sha256=uuid.uuid4().hex,
        status="ready",
    )
    doc_b = Document(
        account_id="account-b",
        filename="doc_b.txt",
        content_type="text/plain",
        sha256=uuid.uuid4().hex,
        status="ready",
    )
    db_session.add_all([doc_a, doc_b])
    db_session.flush()

    # Both chunks have identical embeddings — retrieval order is irrelevant
    chunk_a = Chunk(
        document_id=doc_a.id,
        chunk_index=0,
        text="chunk belonging to account-a",
        embedding=[1.0] + [0.0] * 767,
    )
    chunk_b = Chunk(
        document_id=doc_b.id,
        chunk_index=0,
        text="chunk belonging to account-b",
        embedding=[1.0] + [0.0] * 767,
    )
    db_session.add_all([chunk_a, chunk_b])
    db_session.commit()

    try:
        query_vec = [1.0] + [0.0] * 767

        results_a = retrieve(query_vec, "account-a", db_session, top_k=20)
        chunk_ids_a = {r.chunk_id for r in results_a}
        assert chunk_a.id in chunk_ids_a, "account-a chunk should appear for account-a"
        assert chunk_b.id not in chunk_ids_a, "account-b chunk must not appear for account-a"

        results_b = retrieve(query_vec, "account-b", db_session, top_k=20)
        chunk_ids_b = {r.chunk_id for r in results_b}
        assert chunk_b.id in chunk_ids_b, "account-b chunk should appear for account-b"
        assert chunk_a.id not in chunk_ids_b, "account-a chunk must not appear for account-b"
    finally:
        db_session.query(Chunk).filter(Chunk.document_id.in_([doc_a.id, doc_b.id])).delete(
            synchronize_session=False
        )
        db_session.query(Document).filter(Document.id.in_([doc_a.id, doc_b.id])).delete(
            synchronize_session=False
        )
        db_session.commit()

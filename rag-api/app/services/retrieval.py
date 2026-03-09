"""Retrieval service — finds the most relevant chunks for a query.

Supports three search modes:
  vector  — pgvector cosine similarity (default prior to P3-04)
  bm25    — PostgreSQL full-text search (tsvector / tsquery)
  hybrid  — Reciprocal Rank Fusion of vector + BM25 (default)
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

MAX_TOP_K = 20
_RRF_K = 60  # standard RRF constant


@dataclass
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    chunk_index: int
    page_number: int | None
    text: str
    score: float
    filename: str


def retrieve(
    query_embedding: list[float],
    account_id: str,
    db: Session,
    top_k: int = 5,
    search_mode: str = "hybrid",
    query_text: str = "",
    rerank: bool = False,
) -> list[RetrievedChunk]:
    """Find the top-K most relevant chunks, scoped to account_id.

    search_mode:
      "vector"  — cosine similarity via pgvector
      "bm25"    — PostgreSQL FTS (tsvector @@ tsquery)
      "hybrid"  — Reciprocal Rank Fusion of both (default)

    If query_text is empty and the mode requires BM25, falls back to vector.
    top_k is capped at MAX_TOP_K.

    When rerank=True, fetches top_k * 4 candidates then re-scores them with a
    cross-encoder and returns the top_k highest-scoring results.
    """
    top_k = min(top_k, MAX_TOP_K)

    # Guard: BM25 needs non-empty text; fall back to vector silently.
    if not query_text.strip() and search_mode in ("bm25", "hybrid"):
        search_mode = "vector"

    # Fetch a wider candidate pool when reranking so the cross-encoder has
    # more material to work with.
    fetch_k = top_k * 4 if rerank else top_k

    if search_mode == "vector":
        results = _vector_search(query_embedding, account_id, db, fetch_k)
    elif search_mode == "bm25":
        results = _bm25_search(query_text, account_id, db, fetch_k)
    else:  # hybrid
        results = _hybrid_search(query_embedding, query_text, account_id, db, fetch_k)

    if rerank and results:
        from app.services.reranking import rerank as do_rerank

        results = do_rerank(query_text or "", results, top_k)

    return results[:top_k]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _row_to_chunk(row: object) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=row.id,  # type: ignore[attr-defined]
        document_id=row.document_id,  # type: ignore[attr-defined]
        chunk_index=row.chunk_index,  # type: ignore[attr-defined]
        page_number=row.page_number,  # type: ignore[attr-defined]
        text=row.text,  # type: ignore[attr-defined]
        score=float(row.score),  # type: ignore[attr-defined]
        filename=row.filename,  # type: ignore[attr-defined]
    )


def _vector_search(
    query_embedding: list[float],
    account_id: str,
    db: Session,
    top_k: int,
) -> list[RetrievedChunk]:
    """pgvector cosine similarity search, filtered by account_id."""
    vector_str = f"[{','.join(str(v) for v in query_embedding)}]"

    rows = db.execute(
        text(
            """
            SELECT c.id, c.document_id, c.chunk_index, c.page_number, c.text,
                   1 - (c.embedding <=> CAST(:vec AS vector)) AS score,
                   d.filename
            FROM chunks c
            JOIN documents d ON c.document_id = d.id
            WHERE c.embedding IS NOT NULL
              AND d.account_id = :account_id
            ORDER BY c.embedding <=> CAST(:vec AS vector)
            LIMIT :k
            """
        ),
        {"vec": vector_str, "k": top_k, "account_id": account_id},
    ).fetchall()

    return [_row_to_chunk(row) for row in rows]


def _bm25_search(
    query_text: str,
    account_id: str,
    db: Session,
    top_k: int,
) -> list[RetrievedChunk]:
    """PostgreSQL full-text search using tsvector / tsquery, filtered by account_id."""
    rows = db.execute(
        text(
            """
            SELECT
                c.id, c.document_id, c.chunk_index, c.page_number, c.text,
                d.filename,
                ts_rank(c.search_vector, q.query) AS score
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            CROSS JOIN (SELECT plainto_tsquery('english', :query_text) AS query) q
            WHERE c.search_vector @@ q.query
              AND d.account_id = :account_id
            ORDER BY score DESC
            LIMIT :top_k
            """
        ),
        {"query_text": query_text, "account_id": account_id, "top_k": top_k},
    ).fetchall()

    return [_row_to_chunk(row) for row in rows]


def _hybrid_search(
    query_embedding: list[float],
    query_text: str,
    account_id: str,
    db: Session,
    top_k: int,
) -> list[RetrievedChunk]:
    """Reciprocal Rank Fusion of vector + BM25 results."""
    # Fetch candidates from both paths (wider pool for better fusion)
    vector_results = _vector_search(query_embedding, account_id, db, top_k=20)
    bm25_results = _bm25_search(query_text, account_id, db, top_k=20)

    scores: dict[str, float] = {}
    chunk_map: dict[str, RetrievedChunk] = {}

    for rank, chunk in enumerate(vector_results, start=1):
        cid = str(chunk.chunk_id)
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (_RRF_K + rank)
        chunk_map[cid] = chunk

    for rank, chunk in enumerate(bm25_results, start=1):
        cid = str(chunk.chunk_id)
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (_RRF_K + rank)
        chunk_map[cid] = chunk

    sorted_ids = sorted(scores, key=lambda cid: scores[cid], reverse=True)[:top_k]
    return [chunk_map[cid] for cid in sorted_ids]

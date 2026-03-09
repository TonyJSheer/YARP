"""Retrieval service — finds the most relevant chunks for a query.

Uses pgvector cosine similarity search.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

MAX_TOP_K = 20


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
) -> list[RetrievedChunk]:
    """Find the top-K most similar chunks to a query embedding, scoped to account_id.

    Uses pgvector cosine distance (<=> operator).
    Chunks are filtered via JOIN through documents.account_id — cross-tenant
    data is never returned.
    Returns chunks ordered by similarity (most similar first).
    top_k is capped at MAX_TOP_K.
    """
    top_k = min(top_k, MAX_TOP_K)
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

    return [
        RetrievedChunk(
            chunk_id=row.id,
            document_id=row.document_id,
            chunk_index=row.chunk_index,
            page_number=row.page_number,
            text=row.text,
            score=float(row.score),
            filename=row.filename,
        )
        for row in rows
    ]

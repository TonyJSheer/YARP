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


def retrieve(
    query_embedding: list[float],
    db: Session,
    top_k: int = 5,
) -> list[RetrievedChunk]:
    """Find the top-K most similar chunks to a query embedding.

    Uses pgvector cosine distance (<=> operator).
    Returns chunks ordered by similarity (most similar first).
    top_k is capped at MAX_TOP_K.
    """
    top_k = min(top_k, MAX_TOP_K)
    vector_str = f"[{','.join(str(v) for v in query_embedding)}]"

    rows = db.execute(
        text(
            """
            SELECT id, document_id, chunk_index, page_number, text,
                   1 - (embedding <=> CAST(:vec AS vector)) AS score
            FROM chunks
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> CAST(:vec AS vector)
            LIMIT :k
            """
        ),
        {"vec": vector_str, "k": top_k},
    ).fetchall()

    return [
        RetrievedChunk(
            chunk_id=row.id,
            document_id=row.document_id,
            chunk_index=row.chunk_index,
            page_number=row.page_number,
            text=row.text,
            score=float(row.score),
        )
        for row in rows
    ]

"""Reranking service — re-scores retrieval candidates with a cross-encoder model.

The cross-encoder processes (question, chunk) pairs jointly, giving a more
accurate relevance score than bi-encoder vector search alone. It operates on a
small candidate set (e.g. top_k * 4 → rerank → return top_k), so latency is
acceptable even on CPU (~200–500ms for 20 candidates).
"""

import functools
from typing import Any

from sentence_transformers import CrossEncoder

from app.config import settings


@functools.lru_cache(maxsize=1)
def _get_model() -> Any:
    """Load and cache the CrossEncoder model (loaded once per process)."""
    return CrossEncoder(settings.rerank_model)


def rerank(question: str, chunks: list[Any], top_k: int) -> list[Any]:
    """Re-score chunks against question using cross-encoder. Returns top_k.

    Args:
        question: The user's query string.
        chunks: Candidate chunks (RetrievedChunk instances) to rerank.
        top_k: Number of top chunks to return.

    Returns:
        Up to top_k chunks sorted by cross-encoder score descending.
    """
    if not chunks:
        return chunks

    model = _get_model()
    pairs = [(question, c.text) for c in chunks]
    scores = model.predict(pairs)

    # Cast numpy floats to Python float for JSON serialisability, then sort.
    scored = sorted(
        zip([float(s) for s in scores], chunks),
        key=lambda x: x[0],
        reverse=True,
    )
    return [chunk for _, chunk in scored[:top_k]]

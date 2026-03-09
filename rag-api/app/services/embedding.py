"""Embedding service — generates vector embeddings via sentence-transformers."""

from app.providers import ai_client


def embed_chunks(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for a list of text chunks.

    Returns a list of embedding vectors (one per input text).
    """
    return ai_client.create_embeddings(texts)


def embed_query(text: str) -> list[float]:
    """Generate a single embedding for a query string."""
    return ai_client.create_embeddings([text])[0]

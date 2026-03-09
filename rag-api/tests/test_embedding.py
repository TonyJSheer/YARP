"""Tests for the embedding service."""

from unittest.mock import patch

from app.services.embedding import embed_chunks, embed_query

FAKE_VECTOR = [0.1] * 768


def test_embed_chunks_returns_vectors() -> None:
    with patch("app.providers.ai_client.create_embeddings", return_value=[FAKE_VECTOR]):
        result = embed_chunks(["hello"])
    assert len(result) == 1
    assert len(result[0]) == 768


def test_embed_query_returns_single_vector() -> None:
    with patch("app.providers.ai_client.create_embeddings", return_value=[FAKE_VECTOR]):
        result = embed_query("what is this?")
    assert len(result) == 768


def test_embed_chunks_multiple_texts() -> None:
    fake_vectors = [[0.1] * 768, [0.2] * 768, [0.3] * 768]
    with patch("app.providers.ai_client.create_embeddings", return_value=fake_vectors):
        result = embed_chunks(["text1", "text2", "text3"])
    assert len(result) == 3
    assert all(len(v) == 768 for v in result)

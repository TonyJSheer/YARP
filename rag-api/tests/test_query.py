"""Tests for the query endpoint (POST /query and POST /query/stream)."""

import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.services.retrieval import RetrievedChunk

FAKE_VECTOR = [0.1] * 768


def make_chunk(**kwargs: object) -> RetrievedChunk:
    defaults = dict(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        chunk_index=0,
        page_number=1,
        text="Paris is the capital of France.",
        score=0.95,
        filename="test.txt",
    )
    return RetrievedChunk(**{**defaults, **kwargs})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# POST /query tests
# ---------------------------------------------------------------------------


def test_query_returns_answer_and_citations(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    chunk = make_chunk()
    with (
        patch("app.services.embedding.embed_query", return_value=FAKE_VECTOR),
        patch("app.services.retrieval.retrieve", return_value=[chunk]),
        patch("app.services.generation.generate_answer", return_value=("Paris.", [chunk])),
    ):
        response = client.post(
            "/query", json={"question": "Capital of France?", "top_k": 3}, headers=auth_headers
        )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Paris."
    assert len(body["citations"]) == 1


def test_query_citation_fields(client: TestClient, auth_headers: dict[str, str]) -> None:
    chunk = make_chunk(page_number=3)
    with (
        patch("app.services.embedding.embed_query", return_value=FAKE_VECTOR),
        patch("app.services.retrieval.retrieve", return_value=[chunk]),
        patch("app.services.generation.generate_answer", return_value=("Answer.", [chunk])),
    ):
        response = client.post("/query", json={"question": "Question?"}, headers=auth_headers)

    citation = response.json()["citations"][0]
    assert citation["document_id"] == str(chunk.document_id)
    assert citation["chunk_id"] == str(chunk.chunk_id)
    assert citation["page"] == 3
    assert isinstance(citation["excerpt"], str)


def test_query_excerpt_is_truncated(client: TestClient, auth_headers: dict[str, str]) -> None:
    long_text = "A" * 500
    chunk = make_chunk(text=long_text)
    with (
        patch("app.services.embedding.embed_query", return_value=FAKE_VECTOR),
        patch("app.services.retrieval.retrieve", return_value=[chunk]),
        patch("app.services.generation.generate_answer", return_value=("Answer.", [chunk])),
    ):
        response = client.post("/query", json={"question": "Question?"}, headers=auth_headers)

    excerpt = response.json()["citations"][0]["excerpt"]
    assert len(excerpt) == 200


def test_query_empty_chunks_still_returns_answer(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    with (
        patch("app.services.embedding.embed_query", return_value=FAKE_VECTOR),
        patch("app.services.retrieval.retrieve", return_value=[]),
        patch(
            "app.services.generation.generate_answer",
            return_value=("I don't know.", []),
        ),
    ):
        response = client.post("/query", json={"question": "Question?"}, headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "I don't know."
    assert body["citations"] == []


def test_query_invalid_json_returns_error(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post(
        "/query",
        content=b"not valid json",
        headers={"Content-Type": "application/json", **auth_headers},
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# POST /query/stream tests
# ---------------------------------------------------------------------------


def test_query_stream_returns_sse_content_type(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    with (
        patch("app.services.embedding.embed_query", return_value=FAKE_VECTOR),
        patch("app.services.retrieval.retrieve", return_value=[]),
        patch(
            "app.services.generation.generate_answer_stream",
            return_value=iter(["Hello", "[DONE]"]),
        ),
    ):
        response = client.post("/query/stream", json={"question": "Hi?"}, headers=auth_headers)

    assert "text/event-stream" in response.headers["content-type"]


def test_query_stream_yields_tokens(client: TestClient, auth_headers: dict[str, str]) -> None:
    tokens = ["Hello", " world", "[DONE]"]
    with (
        patch("app.services.embedding.embed_query", return_value=FAKE_VECTOR),
        patch("app.services.retrieval.retrieve", return_value=[]),
        patch("app.services.generation.generate_answer_stream", return_value=iter(tokens)),
    ):
        response = client.post("/query/stream", json={"question": "Hi?"}, headers=auth_headers)

    assert "data: Hello\n\n" in response.text
    assert "data: [DONE]\n\n" in response.text


def test_query_stream_done_event_is_last(client: TestClient, auth_headers: dict[str, str]) -> None:
    tokens = ["Hello", " world", "[DONE]"]
    with (
        patch("app.services.embedding.embed_query", return_value=FAKE_VECTOR),
        patch("app.services.retrieval.retrieve", return_value=[]),
        patch("app.services.generation.generate_answer_stream", return_value=iter(tokens)),
    ):
        response = client.post("/query/stream", json={"question": "Hi?"}, headers=auth_headers)

    assert response.text.endswith("data: [DONE]\n\n")


def test_rest_query_with_rerank(client: TestClient, auth_headers: dict[str, str]) -> None:
    """POST /query accepts rerank=true and returns 200."""
    chunk = make_chunk()
    with (
        patch("app.services.embedding.embed_query", return_value=FAKE_VECTOR),
        patch("app.services.retrieval.retrieve", return_value=[chunk]),
        patch("app.services.generation.generate_answer", return_value=("Answer.", [chunk])),
    ):
        response = client.post(
            "/query",
            json={"question": "Capital of France?", "rerank": True},
            headers=auth_headers,
        )

    assert response.status_code == 200
    assert response.json()["answer"] == "Answer."

"""Tests for the generation service."""

import uuid
from unittest.mock import patch

from app.services import generation
from app.services.generation import SYSTEM_PROMPT, _build_user_prompt
from app.services.retrieval import RetrievedChunk


def make_chunk(**kwargs: object) -> RetrievedChunk:
    defaults = dict(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        chunk_index=0,
        page_number=1,
        text="test text",
        score=0.9,
    )
    return RetrievedChunk(**{**defaults, **kwargs})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# _build_user_prompt tests
# ---------------------------------------------------------------------------


def test_build_user_prompt_includes_chunk_text() -> None:
    chunk = make_chunk(text="Paris is the capital of France.", page_number=2)
    prompt = _build_user_prompt("What is the capital?", [chunk])

    assert "Paris is the capital of France." in prompt
    assert f"doc:{chunk.document_id}" in prompt
    assert "page:2" in prompt
    assert "What is the capital?" in prompt


def test_build_user_prompt_handles_no_chunks() -> None:
    prompt = _build_user_prompt("Any question?", [])

    # No crash; prompt still contains the question
    assert "Any question?" in prompt
    assert "Context:" in prompt


# ---------------------------------------------------------------------------
# generate_answer tests
# ---------------------------------------------------------------------------


def test_generate_answer_calls_chat_completion() -> None:
    chunk = make_chunk(text="Paris is the capital of France.", page_number=2)
    with patch("app.providers.ai_client.chat_completion", return_value="Paris.") as mock_cc:
        answer, cited = generation.generate_answer("What is the capital?", [chunk])

    mock_cc.assert_called_once()
    # First arg is SYSTEM_PROMPT
    assert mock_cc.call_args[0][0] == SYSTEM_PROMPT
    # Second arg (user prompt) contains the chunk text
    assert "Paris is the capital of France." in mock_cc.call_args[0][1]


def test_generate_answer_returns_answer_and_chunks() -> None:
    chunk = make_chunk()
    with patch("app.providers.ai_client.chat_completion", return_value="Test answer."):
        answer, cited = generation.generate_answer("Question?", [chunk])

    assert answer == "Test answer."
    assert cited == [chunk]


def test_generate_answer_no_chunks_still_calls_llm() -> None:
    with patch("app.providers.ai_client.chat_completion", return_value="I don't know.") as mock_cc:
        answer, cited = generation.generate_answer("Question?", [])

    mock_cc.assert_called_once()
    assert answer == "I don't know."
    assert cited == []

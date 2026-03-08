"""AI provider — sentence-transformers for embeddings, Anthropic for generation."""
from collections.abc import Iterator

import anthropic
from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]

from app.config import settings

_embed_model: SentenceTransformer | None = None
_anthropic_client: anthropic.Anthropic | None = None


def get_embed_model() -> SentenceTransformer:
    global _embed_model
    if _embed_model is None:
        _embed_model = SentenceTransformer(settings.embed_model)
    return _embed_model


def get_client() -> anthropic.Anthropic:
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _anthropic_client


def create_embeddings(texts: list[str]) -> list[list[float]]:
    """Generate embeddings using sentence-transformers. Returns one vector per text."""
    model = get_embed_model()
    vectors = model.encode(texts, convert_to_numpy=True)
    return [v.tolist() for v in vectors]


def chat_completion(
    system_prompt: str,
    user_prompt: str,
    model: str | None = None,
) -> str:
    """Generate a chat completion via Anthropic. Returns the response text."""
    message = get_client().messages.create(
        model=model or settings.anthropic_model,
        max_tokens=1024,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return message.content[0].text  # type: ignore[union-attr]


def chat_completion_stream(
    system_prompt: str,
    user_prompt: str,
    model: str | None = None,
) -> Iterator[str]:
    """Stream a chat completion via Anthropic. Yields token strings."""
    with get_client().messages.stream(
        model=model or settings.anthropic_model,
        max_tokens=1024,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    ) as stream:
        yield from stream.text_stream

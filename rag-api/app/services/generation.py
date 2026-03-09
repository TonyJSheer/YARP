"""Generation service — builds prompts and calls the LLM.

System prompt rules:
1. Answer only from the provided context.
2. Cite sources (document_id + page) for each claim.
3. Say "I don't know" if the answer is not found in context.
"""

from collections.abc import Iterator

from app.providers import ai_client
from app.services.retrieval import RetrievedChunk

SYSTEM_PROMPT = """You are a precise question-answering assistant.

Rules:
- Answer ONLY using the context provided below.
- Cite your sources using [doc:<document_id>, page:<page>] after each claim.
- If the answer cannot be found in the context, say "I don't know based on the provided documents."
- Do not fabricate information.
"""


def _build_user_prompt(question: str, chunks: list[RetrievedChunk]) -> str:
    """Build a context-grounded user prompt from retrieved chunks."""
    context_parts = []
    for chunk in chunks:
        page = chunk.page_number if chunk.page_number is not None else "N/A"
        label = f"[doc:{chunk.document_id}, page:{page}]"
        context_parts.append(f"{label}\n{chunk.text}")
    context = "\n\n---\n\n".join(context_parts)
    return f"Context:\n\n{context}\n\nQuestion: {question}"


def generate_answer(
    question: str,
    chunks: list[RetrievedChunk],
) -> tuple[str, list[RetrievedChunk]]:
    """Generate a grounded answer from retrieved chunks.

    Returns (answer_text, cited_chunks).
    """
    user_prompt = _build_user_prompt(question, chunks)
    answer = ai_client.chat_completion(SYSTEM_PROMPT, user_prompt)
    return answer, chunks


def generate_answer_stream(
    question: str,
    chunks: list[RetrievedChunk],
) -> Iterator[str]:
    """Stream answer tokens from the LLM.

    Yields token strings as they arrive.
    Final yield is the string "[DONE]".
    """
    user_prompt = _build_user_prompt(question, chunks)
    yield from ai_client.chat_completion_stream(SYSTEM_PROMPT, user_prompt)
    yield "[DONE]"

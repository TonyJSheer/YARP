# Task 06 — LLM Answer Generation

**Type**: `feature`

**Summary**: Implement the chat completion provider and generation service. `generate_answer()` builds a context-grounded prompt from retrieved chunks, calls the OpenAI chat API, and returns the answer text with the chunks cited. This is the final building block before the query endpoint in Task 07.

---

## Context

**Background**: `generation.py` has `generate_answer()` and `generate_answer_stream()` stubs. `openai_client.py` has `chat_completion()` and `chat_completion_stream()` stubs. `SYSTEM_PROMPT` is already defined in `generation.py`. `RetrievedChunk` from `retrieval.py` (Task 05) provides the chunk data.

**Affected components**:
- [x] Backend API

---

## Requirements

**Functional**:
- `openai_client.chat_completion(system_prompt, user_prompt, model)` calls `chat.completions.create` and returns the response content string
- `generation.generate_answer(question, chunks)`:
  1. Builds a user prompt that includes all chunk texts with source labels (`[doc:<document_id>, page:<page>]`)
  2. Calls `openai_client.chat_completion()` with `SYSTEM_PROMPT` and the built user prompt
  3. Returns `(answer_text, chunks)` — the full chunk list is returned as `cited_chunks` for citation construction in the router (Task 07 will format these into `Citation` objects)
- Default model falls back to `settings.openai_chat_model` when `model=None`
- If no chunks are provided, still call the LLM (it will respond "I don't know")

**Non-functional**:
- The user prompt format must clearly label each chunk's source so the LLM can cite it correctly
- Keep the prompt construction deterministic and testable (pure function of inputs)

---

## Implementation Guidelines

**Files to modify**:
- `app/providers/openai_client.py` — implement `chat_completion()`
- `app/services/generation.py` — implement `generate_answer()`

**Implementation sketch — `openai_client.py`**:

```python
def chat_completion(
    system_prompt: str,
    user_prompt: str,
    model: str | None = None,
) -> str:
    response = get_client().chat.completions.create(
        model=model or settings.openai_chat_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return response.choices[0].message.content or ""
```

**Implementation sketch — `generation.py`**:

```python
from app.providers import openai_client

def _build_user_prompt(question: str, chunks: list[RetrievedChunk]) -> str:
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
    user_prompt = _build_user_prompt(question, chunks)
    answer = openai_client.chat_completion(SYSTEM_PROMPT, user_prompt)
    return answer, chunks
```

---

## API Changes

None — `generate_answer()` is an internal service.

---

## Test Requirements

**All OpenAI calls must be mocked.**

**`tests/test_generation.py`** (new file):

- `test_build_user_prompt_includes_chunk_text` — call `_build_user_prompt()` with known chunks; assert chunk text and source labels appear in output
- `test_build_user_prompt_handles_no_chunks` — empty chunk list produces a prompt with empty context (no crash)
- `test_generate_answer_calls_chat_completion` — mock `openai_client.chat_completion`; assert it is called once with `SYSTEM_PROMPT` and a prompt containing the chunk text
- `test_generate_answer_returns_answer_and_chunks` — mock returns `"Test answer"`; assert `generate_answer()` returns `("Test answer", chunks)`
- `test_generate_answer_no_chunks_still_calls_llm` — assert LLM is called even when `chunks=[]`

**Mocking pattern**:
```python
from unittest.mock import patch
from app.services import generation
from app.services.retrieval import RetrievedChunk

def make_chunk(**kwargs) -> RetrievedChunk:
    defaults = dict(chunk_id=uuid.uuid4(), document_id=uuid.uuid4(),
                    chunk_index=0, page_number=1, text="test text", score=0.9)
    return RetrievedChunk(**{**defaults, **kwargs})

def test_generate_answer_calls_chat_completion() -> None:
    chunk = make_chunk(text="Paris is the capital of France.", page_number=2)
    with patch("app.providers.openai_client.chat_completion", return_value="Paris.") as mock_cc:
        answer, cited = generation.generate_answer("What is the capital?", [chunk])
    mock_cc.assert_called_once()
    assert answer == "Paris."
    assert cited == [chunk]
```

---

## Acceptance Criteria

- [ ] `generate_answer()` returns `(str, list[RetrievedChunk])`
- [ ] User prompt contains chunk texts and source labels `[doc:..., page:...]`
- [ ] `chat_completion()` is called with `SYSTEM_PROMPT` as the system message
- [ ] Works correctly with zero chunks (no crash)
- [ ] `make test` passes with all OpenAI calls mocked
- [ ] `make lint && make typecheck` passes

---

## Validation Steps

```bash
make test
make lint
make typecheck
```

Full end-to-end validation comes in Task 07 when the query endpoint is wired up.

---

## Risks

- LLM citation format depends on prompt engineering — the citation labels `[doc:..., page:...]` in the prompt must match what the router expects in Task 07 when parsing citations from the answer text. For Phase 1, the router will pass the raw `chunks` list directly as citations rather than parsing the LLM output, so this is not a blocker.
- `response.choices[0].message.content` can be `None` in edge cases (content filtering) — the `or ""` fallback handles this.
- `_build_user_prompt` should be importable from tests for direct unit testing — do not make it a private name-mangled method.

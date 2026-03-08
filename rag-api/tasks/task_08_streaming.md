# Task 08 — Streaming Responses

**Type**: `feature`

**Summary**: Implement `POST /query/stream` — runs the same retrieve pipeline as Task 07, but streams LLM answer tokens to the client incrementally via Server-Sent Events (SSE). Each SSE event carries one token; a final `[DONE]` event signals completion.

---

## Context

**Background**: The `query_stream` router stub already exists. `openai_client.chat_completion_stream()` stub exists in `openai_client.py`. `generation.generate_answer_stream()` stub exists in `generation.py`. This task implements both stubs and wires up the streaming router.

**Affected components**:
- [x] Backend API

---

## Requirements

**Functional**:
- `openai_client.chat_completion_stream(system_prompt, user_prompt, model)` calls `chat.completions.create(stream=True)` and yields token strings from each chunk delta
- `generation.generate_answer_stream(question, chunks)` builds the same prompt as `generate_answer()` and yields tokens from `openai_client.chat_completion_stream()`, finishing with a `"[DONE]"` yield
- `POST /query/stream`:
  1. Decodes `QueryRequest` from request body
  2. Embeds question, retrieves chunks (same as Task 07)
  3. Returns a `StreamingResponse` with `media_type="text/event-stream"`
  4. Generator yields SSE-formatted events: `f"data: {token}\n\n"` per token, `"data: [DONE]\n\n"` as the final event

**Non-functional**:
- Uses `StreamingResponse` from FastAPI/Starlette
- The SSE generator must be a regular (sync) generator wrapped or an async generator — use whichever is simpler with the sync OpenAI SDK
- Default model falls back to `settings.openai_chat_model`

---

## Implementation Guidelines

**Files to modify**:
- `app/providers/openai_client.py` — implement `chat_completion_stream()`
- `app/services/generation.py` — implement `generate_answer_stream()`
- `app/routers/query.py` — implement `query_stream()`

**Implementation sketch — `openai_client.py`**:

```python
def chat_completion_stream(
    system_prompt: str,
    user_prompt: str,
    model: str | None = None,
) -> Iterator[str]:
    stream = get_client().chat.completions.create(
        model=model or settings.openai_chat_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        stream=True,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta
```

**Implementation sketch — `generation.py`**:

```python
def generate_answer_stream(
    question: str,
    chunks: list[RetrievedChunk],
) -> Iterator[str]:
    user_prompt = _build_user_prompt(question, chunks)
    yield from openai_client.chat_completion_stream(SYSTEM_PROMPT, user_prompt)
    yield "[DONE]"
```

**Implementation sketch — `query.py` router**:

```python
@router.post("/stream")
async def query_stream(request: Request, db: Session = Depends(get_db)) -> StreamingResponse:
    req = msgspec.json.decode(await request.body(), type=QueryRequest)

    query_vec = embedding.embed_query(req.question)
    chunks = retrieval.retrieve(query_vec, db, top_k=req.top_k)

    def event_generator() -> Iterator[str]:
        for token in generation.generate_answer_stream(req.question, chunks):
            yield f"data: {token}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

---

## API Changes

**Endpoint**: `POST /query/stream` (existing stub — now implemented)

**Request**: same as `POST /query`
```json
{"question": "...", "top_k": 5}
```

**Response**: `Content-Type: text/event-stream`
```
data: Paris

data:  is

data:  the

data:  capital.

data: [DONE]

```

---

## Test Requirements

**All OpenAI calls must be mocked.**

**`tests/test_query.py`** additions:

- `test_query_stream_returns_sse_content_type` — mock `embed_query`, `retrieve`, `generate_answer_stream`; POST to `/query/stream`; assert `Content-Type` header is `text/event-stream`
- `test_query_stream_yields_tokens` — mock `generate_answer_stream` to yield `["Hello", " world", "[DONE]"]`; assert response body contains `"data: Hello\n\n"` and `"data: [DONE]\n\n"`
- `test_query_stream_done_event_is_last` — assert `[DONE]` is the final event in the stream

**Mocking pattern**:
```python
def test_query_stream_yields_tokens(client: TestClient) -> None:
    tokens = ["Hello", " world", "[DONE]"]
    with (
        patch("app.services.embedding.embed_query", return_value=[0.1] * 1536),
        patch("app.services.retrieval.retrieve", return_value=[]),
        patch("app.services.generation.generate_answer_stream", return_value=iter(tokens)),
    ):
        response = client.post(
            "/query/stream",
            json={"question": "Hi?"},
        )

    assert "data: Hello\n\n" in response.text
    assert response.text.endswith("data: [DONE]\n\n")
```

---

## Acceptance Criteria

- [ ] `POST /query/stream` returns `Content-Type: text/event-stream`
- [ ] Each token arrives as `data: <token>\n\n`
- [ ] Final event is `data: [DONE]\n\n`
- [ ] Empty chunk list does not crash the stream (LLM still generates a response)
- [ ] `make test` passes with all OpenAI calls mocked
- [ ] `make lint && make typecheck` passes

---

## Validation Steps

```bash
# Stream tokens with curl (requires real OPENAI_API_KEY):
curl -N -X POST http://localhost:8000/query/stream \
  -H "Content-Type: application/json" \
  -d '{"question": "What does the document say?", "top_k": 3}'
# Tokens should appear incrementally in the terminal

make test
make lint
make typecheck
```

---

## Risks

- The sync OpenAI streaming iterator is consumed inside a sync generator (`event_generator`), which is fine inside `StreamingResponse` — Starlette iterates the generator in a thread pool for sync generators
- If the client disconnects mid-stream, the generator will raise `GeneratorExit` — this is handled automatically by Python and does not need explicit error handling
- `[DONE]` is yielded by `generate_answer_stream()`, not the router — this keeps the router clean but means the router must not add its own `[DONE]` event
- `chat_completion_stream()` in `openai_client.py` uses `yield` making it a generator — the `chat_completion_stream` stub currently returns `Iterator[str]`; ensure the implementation signature matches (it does, since a generator function satisfies `Iterator[str]`)

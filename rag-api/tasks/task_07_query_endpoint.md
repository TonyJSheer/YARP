# Task 07 — Query Endpoint

**Type**: `feature`

**Summary**: Wire up `POST /query` — decode the request, embed the question, retrieve top-K chunks, generate a grounded answer, and return `{"answer": "...", "citations": [...]}`. This is the first end-to-end RAG request in the system.

---

## Context

**Background**: The query router stub decodes `QueryRequest` via msgspec but raises `NotImplementedError`. `QueryResponse` and `Citation` msgspec Structs are defined in `app/schemas/query.py`. `embedding.embed_query()` (Task 04), `retrieval.retrieve()` (Task 05), and `generation.generate_answer()` (Task 06) are all implemented and ready to compose.

**Affected components**:
- [x] Backend API

---

## Requirements

**Functional**:
- `POST /query` accepts `{"question": "...", "top_k": 5}` (JSON body)
- Pipeline: embed question → retrieve top-K chunks → generate answer → return response
- Response: `{"answer": "...", "citations": [{"document_id": "...", "chunk_id": "...", "page": N, "excerpt": "..."}]}`
- `excerpt` is the first 200 characters of the chunk text
- `top_k` defaults to 5 if not provided; capped at 20 (enforced by `retrieval.retrieve()`)
- If no chunks are found, the LLM is still called and will respond "I don't know"
- On error: return `500` with standard error envelope

**Non-functional**:
- Response is encoded with `msgspec.json.encode()` and returned as a `Response(media_type="application/json")`
- No business logic in the router — all work delegated to services

---

## Implementation Guidelines

**Files to modify**:
- `app/routers/query.py` — implement `query_endpoint()`

**Implementation sketch**:

```python
from app.services import embedding, retrieval, generation
from app.schemas.query import Citation, QueryRequest, QueryResponse

@router.post("", response_model=None)
async def query_endpoint(request: Request, db: Session = Depends(get_db)) -> Response:
    req = msgspec.json.decode(await request.body(), type=QueryRequest)

    query_vec = embedding.embed_query(req.question)
    chunks = retrieval.retrieve(query_vec, db, top_k=req.top_k)
    answer, cited_chunks = generation.generate_answer(req.question, chunks)

    citations = [
        Citation(
            document_id=str(c.document_id),
            chunk_id=str(c.chunk_id),
            page=c.page_number,
            excerpt=c.text[:200],
        )
        for c in cited_chunks
    ]

    result = QueryResponse(answer=answer, citations=citations)
    return Response(
        content=msgspec.json.encode(result),
        media_type="application/json",
    )
```

---

## API Changes

**Endpoint**: `POST /query` (existing stub — now implemented)

**Request**:
```json
{"question": "What is the capital of France?", "top_k": 5}
```

**Response** `200`:
```json
{
  "answer": "Paris is the capital of France [doc:abc-123, page:2].",
  "citations": [
    {
      "document_id": "abc-123",
      "chunk_id": "def-456",
      "page": 2,
      "excerpt": "Paris is the capital of France..."
    }
  ]
}
```

**Error** `500`:
```json
{"error": {"code": "query_failed", "message": "An error occurred processing your query.", "field": null}}
```

---

## Test Requirements

**All OpenAI calls must be mocked.**

**`tests/test_query.py`** — replace all stubs with real tests:

- `test_query_returns_answer_and_citations` — mock `embed_query`, `retrieve`, `generate_answer`; POST to `/query`; assert 200, `answer` is a non-empty string, `citations` is a list
- `test_query_citation_fields` — assert each citation has `document_id`, `chunk_id`, `page`, `excerpt` fields with correct types
- `test_query_excerpt_is_truncated` — use a chunk with text > 200 chars; assert `excerpt` is exactly 200 chars
- `test_query_empty_chunks_still_returns_answer` — mock `retrieve` to return `[]`; assert endpoint returns 200 with answer (LLM says "I don't know")
- `test_query_invalid_json_returns_error` — POST with invalid JSON body; assert non-200 response

**Mocking pattern**:
```python
from unittest.mock import patch, MagicMock
from app.services.retrieval import RetrievedChunk

def make_chunk() -> RetrievedChunk:
    return RetrievedChunk(chunk_id=uuid.uuid4(), document_id=uuid.uuid4(),
                          chunk_index=0, page_number=1, text="Paris is the capital.", score=0.95)

def test_query_returns_answer_and_citations(client: TestClient) -> None:
    chunk = make_chunk()
    with (
        patch("app.services.embedding.embed_query", return_value=[0.1] * 1536),
        patch("app.services.retrieval.retrieve", return_value=[chunk]),
        patch("app.services.generation.generate_answer", return_value=("Paris.", [chunk])),
    ):
        response = client.post("/query", json={"question": "Capital of France?", "top_k": 3})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Paris."
    assert len(body["citations"]) == 1
```

---

## Acceptance Criteria

- [ ] `POST /query` returns `200` with `answer` and `citations` fields
- [ ] Citations include `document_id`, `chunk_id`, `page`, `excerpt` (≤ 200 chars)
- [ ] Pipeline order: embed → retrieve → generate (never skipped)
- [ ] Empty retrieval result does not crash — LLM is still called
- [ ] `make test` passes with all OpenAI calls mocked
- [ ] `make lint && make typecheck` passes

---

## Validation Steps

```bash
# End-to-end with a real OPENAI_API_KEY in .env:
# 1. Upload a document
curl -X POST http://localhost:8000/documents -F "file=@test.txt"

# 2. Query it
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What does the document say?", "top_k": 3}'

make test
make lint
make typecheck
```

---

## Risks

- The router uses `msgspec.json.decode` on raw request bytes — if the client sends non-JSON or missing fields, msgspec raises `msgspec.ValidationError`. Catch this and return a `400` rather than letting it propagate as a `500`.
- `embed_query` calls the OpenAI API synchronously in an async route — acceptable for Phase 1. FastAPI runs sync functions in a thread pool automatically if the endpoint is `async def` and the called function is not awaited, but since all our service functions are sync, this is fine.

# Task 04 — Embeddings

**Type**: `feature`

**Summary**: Implement the OpenAI embeddings provider and embedding service, then extend `ingest()` to generate and store embedding vectors for every chunk. After this task, all `Chunk` rows will have a populated `embedding` column and `documents.status` will be `'ready'`.

---

## Context

**Background**: Task 03 left `Chunk.embedding = NULL` and `documents.status = 'chunked'`. This task fills in the two stubs — `openai_client.create_embeddings()` and `embedding.embed_chunks()` — and wires them into `ingest()` as the final pipeline step. Both `OPENAI_API_KEY` and `OPENAI_EMBED_MODEL` are already in `config.py` and `.env.example`.

**Affected components**:
- [x] Backend API

---

## Requirements

**Functional**:
- `openai_client.create_embeddings(texts, model)` calls the OpenAI embeddings API and returns one `list[float]` per input text
- `embedding.embed_chunks(texts)` batches texts into groups of `EMBED_BATCH_SIZE` (100), calls `create_embeddings()` per batch, retries once on `openai.APIError`, and returns a flat list of vectors
- `embedding.embed_query(text)` returns a single embedding vector for a query string (no batching needed)
- `ingest()` extended: after chunking, call `embed_chunks()` with all chunk texts, write vectors back to the `Chunk` rows, set `doc.status = 'ready'`, commit
- On embedding failure: set `doc.status = 'failed'`, commit, re-raise so the router returns `422`
- `POST /documents` response `status` field changes from `'chunked'` → `'ready'`

**Non-functional**:
- Never log or store the raw API key
- Default model falls back to `settings.openai_embed_model` when `model=None`

---

## Implementation Guidelines

**Files to modify**:
- `app/providers/openai_client.py` — implement `create_embeddings()`
- `app/services/embedding.py` — implement `embed_chunks()` and `embed_query()`
- `app/services/ingestion.py` — extend `ingest()` with embedding step; update final status to `'ready'`

**Files to modify (tests)**:
- `tests/test_documents.py` — update status assertions from `'chunked'` → `'ready'`

**Implementation sketch — `openai_client.py`**:

```python
def create_embeddings(texts: list[str], model: str | None = None) -> list[list[float]]:
    response = get_client().embeddings.create(
        input=texts,
        model=model or settings.openai_embed_model,
    )
    return [item.embedding for item in response.data]
```

**Implementation sketch — `embedding.py`**:

```python
import openai
from app.providers import openai_client

def embed_chunks(texts: list[str]) -> list[list[float]]:
    results: list[list[float]] = []
    for i in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[i : i + EMBED_BATCH_SIZE]
        try:
            results.extend(openai_client.create_embeddings(batch))
        except openai.APIError:
            # Retry once
            results.extend(openai_client.create_embeddings(batch))
    return results

def embed_query(text: str) -> list[float]:
    return openai_client.create_embeddings([text])[0]
```

**`ingest()` extension** (add after chunk storage, before returning):

```python
    try:
        vectors = embedding.embed_chunks([c.text for c in chunk_models])
        for chunk, vector in zip(chunk_models, vectors):
            chunk.embedding = vector
        doc.status = "ready"
        db.commit()
    except Exception:
        doc.status = "failed"
        db.commit()
        raise
```

---

## API Changes

`POST /documents` response: `status` changes from `"chunked"` → `"ready"`.

---

## Test Requirements

**All OpenAI calls must be mocked — no real API calls in CI.**

**`tests/test_documents.py`**:
- Update all `status == "chunked"` assertions → `status == "ready"`
- Add `test_upload_chunks_have_embeddings` — upload a `.txt` file with mocked `embed_chunks` returning fake vectors; assert `Chunk.embedding` is not `None`

**`tests/test_embedding.py`** (new file):
- `test_embed_chunks_batches_correctly` — mock `create_embeddings`; assert it is called `ceil(n/100)` times for `n` texts
- `test_embed_chunks_retries_on_api_error` — mock `create_embeddings` to raise `openai.APIError` once then succeed; assert result is returned and `create_embeddings` was called twice for that batch
- `test_embed_chunks_raises_after_two_failures` — mock `create_embeddings` to always raise; assert the exception propagates
- `test_embed_query_returns_single_vector` — mock `create_embeddings`; assert a single `list[float]` is returned

**Mocking pattern**:
```python
from unittest.mock import patch

def test_embed_chunks_batches_correctly() -> None:
    fake_vector = [0.1] * 1536
    with patch("app.providers.openai_client.get_client") as mock_client:
        mock_client.return_value.embeddings.create.return_value.data = [
            type("E", (), {"embedding": fake_vector})() for _ in range(...)
        ]
        ...
```

---

## Acceptance Criteria

- [ ] `POST /documents` returns `status == "ready"` after successful ingestion
- [ ] All `Chunk` rows have non-null `embedding` vectors after upload
- [ ] `embed_chunks()` sends texts in batches of ≤ 100
- [ ] A single `openai.APIError` is retried; a second failure propagates
- [ ] `make test` passes with all OpenAI calls mocked
- [ ] `make lint && make typecheck` passes

---

## Validation Steps

```bash
# With a real OPENAI_API_KEY in .env:
curl -X POST http://localhost:8000/documents -F "file=@test.txt"
# Expected: {"document_id": "...", "status": "ready"}

docker compose exec postgres psql -U rag -d rag \
  -c "SELECT chunk_index, embedding IS NOT NULL as has_embedding FROM chunks LIMIT 5;"

make test
make lint
make typecheck
```

---

## Risks

- OpenAI rate limits: for large documents the batch loop may hit rate limits. For Phase 1 (small files) this is acceptable — no rate-limit handling needed yet.
- `test_documents.py` assertions on `status` must be updated; there are at least two (`test_upload_txt_returns_201`, `test_upload_creates_db_record`).
- The `openai` package raises `openai.APIError` as the base class for transient errors — import it directly from the `openai` package, not from the client.

# Task P3-05 — Reranking (Cross-Encoder)

**Type**: `feature`
**Priority**: P2

**Summary**: After retrieval, optionally re-score candidates with a cross-encoder model and return the top-k by cross-encoder relevance. Improves precision when retrieval candidates include partially relevant chunks. Opt-in via `rerank=true`.

**Depends on**: P3-04 (hybrid search — more candidates to rerank makes this more valuable)

---

## Context

**The problem**: Bi-encoder vector search scores each chunk independently against the query. A chunk that mentions a keyword but doesn't directly answer the question can score higher than a shorter, more directly relevant chunk.

**Cross-encoders** process the (question, chunk) pair jointly, giving a more accurate relevance score. They're slower than vector search but operate on a small candidate set (e.g., 20 candidates → rerank → return top 5), so the latency cost is acceptable.

---

## Requirements

**Functional**:
- `query_documents` MCP tool gains optional `rerank: bool = False` parameter
- `POST /query` REST body gains optional `"rerank": false` field
- When `rerank=true`: retrieve `top_k * 4` candidates, rerank all of them, return top `top_k`
- Cross-encoder model is configurable via `RERANK_MODEL` config (default: `cross-encoder/ms-marco-MiniLM-L-6-v2`)
- Model is pre-downloaded at Docker build time (same pattern as the embedding model)
- When `rerank=false` (default): behaviour is identical to Phase 3 without this task

**Non-functional**:
- Reranking adds ~200–500ms on a CPU for 20 candidates — acceptable for Phase 3 scale
- Cross-encoder is loaded once and cached (not re-loaded on every request)

---

## Implementation Guidelines

**New package**: none — `sentence-transformers` already installed, cross-encoders are included

**Files to create**:
- `app/services/reranking.py`

**Files to modify**:
- `app/services/retrieval.py` — `retrieve()` accepts `rerank: bool = False`
- `app/schemas/query.py` — add `rerank: bool = False` to `QueryRequest`
- `app/routers/query.py` — pass `rerank` from request to `retrieve()`
- `app/mcp_server.py` — add `rerank` parameter to `query_documents`
- `app/config.py` — add `rerank_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"`
- `Dockerfile` — pre-download rerank model at build time

**Reranking service**:

```python
# app/services/reranking.py
import functools
from sentence_transformers import CrossEncoder
from app.config import settings

@functools.lru_cache(maxsize=1)
def _get_model() -> CrossEncoder:  # type: ignore[type-arg]
    return CrossEncoder(settings.rerank_model)

def rerank(question: str, chunks: list[Any], top_k: int) -> list[Any]:
    """Re-score chunks against question using cross-encoder. Returns top_k."""
    if not chunks:
        return chunks

    model = _get_model()
    pairs = [(question, c.text) for c in chunks]
    scores = model.predict(pairs)  # type: ignore[no-untyped-call]

    scored = sorted(zip(scores, chunks), key=lambda x: x[0], reverse=True)
    return [chunk for _, chunk in scored[:top_k]]
```

**Retrieval integration**:

```python
# app/services/retrieval.py

def retrieve(
    query_embedding: list[float],
    account_id: str,
    db: Session,
    top_k: int = 5,
    search_mode: str = "hybrid",
    query_text: str = "",
    rerank: bool = False,
) -> list[RetrievedChunk]:
    # Fetch more candidates when reranking
    fetch_k = top_k * 4 if rerank else top_k

    if search_mode == "vector":
        results = _vector_search(query_embedding, account_id, db, fetch_k)
    elif search_mode == "bm25":
        results = _bm25_search(query_text, account_id, db, fetch_k)
    else:
        results = _hybrid_search(query_embedding, query_text, account_id, db, fetch_k)

    if rerank and results:
        from app.services.reranking import rerank as do_rerank
        results = do_rerank(query_text or "", results, top_k)

    return results[:top_k]
```

**Dockerfile addition**:

```dockerfile
# Pre-download rerank model
ARG RERANK_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
RUN uv run python -c "from sentence_transformers import CrossEncoder; CrossEncoder('${RERANK_MODEL}')"
```

---

## Test Requirements

- `test_rerank_reorders_chunks` — create two chunks where vector order is [B, A] but A is more relevant; with `rerank=True`, assert A comes first
- `test_rerank_false_skips_cross_encoder` — mock CrossEncoder; call `retrieve(rerank=False)`; assert CrossEncoder never instantiated
- `test_rerank_truncates_to_top_k` — retrieve with `top_k=2, rerank=True`; assert exactly 2 chunks returned
- `test_rest_query_with_rerank` — `POST /query` with `{"question": "...", "rerank": true}`; assert 200
- `test_mcp_query_with_rerank` — call `query_documents(question="...", rerank=True)`; assert chunks returned

---

## Acceptance Criteria

- [ ] `rerank=true` re-scores candidates and returns top-k by cross-encoder score
- [ ] `rerank=false` (default) behaves identically to pre-reranking behaviour
- [ ] Cross-encoder model pre-downloaded in Docker image (no download at runtime)
- [ ] `POST /query` accepts `"rerank": true`
- [ ] `query_documents` MCP tool accepts `rerank=true`
- [ ] `make test` passes
- [ ] `make lint && make typecheck` passes

---

## Risks

- Cross-encoder adds latency. On first call it loads the model from disk (~80MB). Subsequent calls use the cached model. First-call latency may be 2–5 seconds — acceptable for an opt-in feature.
- `lru_cache` on the model loader means the model stays in memory for the process lifetime. On the cloud (1GB RAM machine) this is fine. Monitor memory if scaling.
- `CrossEncoder.predict()` returns numpy floats — ensure these are cast to Python `float` before serialising to JSON.

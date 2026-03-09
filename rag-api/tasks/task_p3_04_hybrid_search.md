# Task P3-04 — Hybrid Search (BM25 + Vector)

**Type**: `feature`
**Priority**: P2

**Summary**: Add BM25 keyword search alongside the existing vector search, then merge results using Reciprocal Rank Fusion (RRF). Implemented entirely in PostgreSQL — no new services. Improves recall for exact keyword queries that vector search misses.

**Depends on**: P3-01, P3-02

---

## Context

**The problem**: Vector search finds semantically similar chunks but struggles with exact keyword matches. A query for "RFC 7519" or "ISO 8601" returns poor results because the vector space treats these as opaque tokens. BM25 (term frequency / inverse document frequency) handles exact and rare terms much better.

**Approach**: PostgreSQL full-text search (`tsvector` / `tsquery`) provides BM25-style ranking via `ts_rank`. No additional service is needed. Add a `tsvector` generated column to `chunks`, index it with GIN, run both searches in parallel, merge with RRF.

---

## Requirements

**Functional**:
- New `chunks.search_vector` column: `TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', text)) STORED`
- GIN index on `search_vector` for fast full-text lookup
- `retrieval.retrieve()` accepts a `search_mode: str = "hybrid"` parameter: `"vector"`, `"bm25"`, or `"hybrid"` (default)
- Hybrid mode runs both searches, merges with RRF, returns top-k by combined score
- `query_documents` MCP tool gains an optional `search_mode` parameter
- `POST /query` REST body gains an optional `"search_mode"` field

**Non-functional**:
- Both searches run in the same database transaction (no serial round-trips)
- RRF constant `k = 60` (standard default)
- Existing behaviour is preserved when `search_mode="vector"` — no regression

---

## Implementation Guidelines

**Migration**:

```python
# migrations/versions/0005_add_search_vector.py

def upgrade() -> None:
    # Add generated tsvector column
    op.execute("""
        ALTER TABLE chunks
        ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (to_tsvector('english', text)) STORED
    """)
    # GIN index for fast FTS
    op.execute("CREATE INDEX ix_chunks_search_vector ON chunks USING GIN (search_vector)")

def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chunks_search_vector")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS search_vector")
```

> Note: `GENERATED ALWAYS AS ... STORED` is available in PostgreSQL 12+. Neon and the `pgvector/pgvector:pg16` image both support this.

**Retrieval service — hybrid search**:

```python
# app/services/retrieval.py

def retrieve(
    query_embedding: list[float],
    account_id: str,
    db: Session,
    top_k: int = 5,
    search_mode: str = "hybrid",
    query_text: str = "",  # required for bm25 / hybrid modes
) -> list[RetrievedChunk]:
    if search_mode == "vector":
        return _vector_search(query_embedding, account_id, db, top_k)
    elif search_mode == "bm25":
        return _bm25_search(query_text, account_id, db, top_k)
    else:  # hybrid
        return _hybrid_search(query_embedding, query_text, account_id, db, top_k)


def _hybrid_search(
    query_embedding: list[float],
    query_text: str,
    account_id: str,
    db: Session,
    top_k: int,
) -> list[RetrievedChunk]:
    """Reciprocal Rank Fusion of vector + BM25 results."""
    k = 60  # RRF constant

    # Vector candidates (top 20)
    vector_results = _vector_search(query_embedding, account_id, db, top_k=20)
    # BM25 candidates (top 20)
    bm25_results = _bm25_search(query_text, account_id, db, top_k=20)

    # Build RRF score map: chunk_id → combined score
    scores: dict[str, float] = {}
    chunk_map: dict[str, RetrievedChunk] = {}

    for rank, chunk in enumerate(vector_results, start=1):
        cid = str(chunk.chunk_id)
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
        chunk_map[cid] = chunk

    for rank, chunk in enumerate(bm25_results, start=1):
        cid = str(chunk.chunk_id)
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
        chunk_map[cid] = chunk

    # Sort by combined RRF score, return top_k
    sorted_ids = sorted(scores, key=lambda cid: scores[cid], reverse=True)[:top_k]
    return [chunk_map[cid] for cid in sorted_ids]


def _bm25_search(
    query_text: str,
    account_id: str,
    db: Session,
    top_k: int,
) -> list[RetrievedChunk]:
    """PostgreSQL full-text search using tsvector / tsquery."""
    sql = text("""
        SELECT
            c.id, c.document_id, c.chunk_index, c.page_number, c.text,
            d.filename,
            ts_rank(c.search_vector, query) AS score
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        CROSS JOIN plainto_tsquery('english', :query_text) AS query
        WHERE c.search_vector @@ query
          AND d.account_id = :account_id
        ORDER BY score DESC
        LIMIT :top_k
    """)
    rows = db.execute(sql, {
        "query_text": query_text,
        "account_id": account_id,
        "top_k": top_k,
    }).fetchall()
    return [_row_to_chunk(row) for row in rows]
```

**Router + MCP changes**:

```python
# app/schemas/query.py — add field
class QueryRequest(msgspec.Struct):
    question: str
    top_k: int = 5
    search_mode: str = "hybrid"  # "vector" | "bm25" | "hybrid"

# app/routers/query.py — pass search_mode
chunks = retrieval.retrieve(
    query_vec, account_id, db,
    top_k=req.top_k,
    search_mode=req.search_mode,
    query_text=req.question,
)

# app/mcp_server.py — add search_mode param
async def query_documents(
    question: str,
    top_k: int = 5,
    search_mode: str = "hybrid",
) -> dict[str, Any]:
    ...
    chunks = retrieval.retrieve(
        query_emb, account_id, db,
        top_k=top_k,
        search_mode=search_mode,
        query_text=question,
    )
```

---

## Test Requirements

- `test_bm25_finds_exact_keyword` — insert chunk with "RFC 7519"; vector search for "JWT specification" may miss it; BM25 search for "RFC 7519" must find it
- `test_vector_finds_semantic_match` — insert chunk about "token authentication"; vector search for "JWT" finds it; BM25 search for "JWT" may miss if that exact token isn't present
- `test_hybrid_merges_both` — insert two chunks: one BM25-only match, one vector-only match; hybrid search returns both
- `test_hybrid_is_default` — call `retrieve()` without `search_mode`; assert both result types present
- `test_account_isolation_preserved` — hybrid search still only returns the caller's chunks

---

## Acceptance Criteria

- [ ] Migration applies cleanly; `chunks.search_vector` column exists with GIN index
- [ ] `search_mode="vector"` returns same results as before (no regression)
- [ ] `search_mode="bm25"` returns results ranked by FTS score
- [ ] `search_mode="hybrid"` (default) merges both via RRF
- [ ] `POST /query` accepts `"search_mode"` field
- [ ] `query_documents` MCP tool accepts `search_mode` parameter
- [ ] `make test` passes
- [ ] `make lint && make typecheck` passes

---

## Risks

- `plainto_tsquery` tokenises the query — for very short queries (single word) BM25 results may be sparse. This is acceptable; hybrid mode ensures vector results are also included.
- Generated column syntax is PostgreSQL-specific — confirm Neon supports `GENERATED ALWAYS AS ... STORED` (it does, as of PostgreSQL 12)
- If `query_text` is empty and `search_mode="bm25"` or `"hybrid"`, BM25 returns no results. Guard with: if `not query_text.strip()`, fall back to vector-only silently.

# Task 05 — Vector Retrieval

**Type**: `feature`

**Summary**: Implement `retrieval.retrieve()` — embed the user query and run a pgvector cosine similarity search against the `chunks` table, returning the top-K most relevant chunks with metadata. This service is a prerequisite for the query endpoint in Task 07.

---

## Context

**Background**: After Tasks 03–04, all `Chunk` rows have populated `embedding` vectors. The `retrieval.py` service has a `retrieve()` stub and a `RetrievedChunk` dataclass already defined. The `embedding.embed_query()` function (implemented in Task 04) provides query embedding. This task wires them together with a pgvector SQL query.

**Affected components**:
- [x] Backend API

---

## Requirements

**Functional**:
- `retrieve(query_embedding, db, top_k=5)` executes a cosine distance search using pgvector's `<=>` operator against `chunks.embedding`
- Returns a list of `RetrievedChunk` dataclasses ordered by similarity (lowest distance = most similar first)
- Returns at most `top_k` results; returns an empty list when no chunks exist
- Each `RetrievedChunk` is populated with: `chunk_id`, `document_id`, `chunk_index`, `page_number`, `text`, `score` (cosine similarity, i.e. `1 - distance`)

**Non-functional**:
- Query must use SQLAlchemy's `text()` or ORM expressions — no raw string concatenation
- `top_k` is bounded to a maximum of 20 to prevent runaway queries

---

## Implementation Guidelines

**Files to modify**:
- `app/services/retrieval.py` — implement `retrieve()`

**Files to modify (tests)**:
- `tests/test_retrieval.py` — replace all stubs with real tests

**Implementation sketch — `retrieval.py`**:

```python
from sqlalchemy import text
from app.models.chunk import Chunk

MAX_TOP_K = 20

def retrieve(
    query_embedding: list[float],
    db: Session,
    top_k: int = 5,
) -> list[RetrievedChunk]:
    top_k = min(top_k, MAX_TOP_K)
    vector_str = f"[{','.join(str(v) for v in query_embedding)}]"

    rows = db.execute(
        text(
            """
            SELECT id, document_id, chunk_index, page_number, text,
                   1 - (embedding <=> CAST(:vec AS vector)) AS score
            FROM chunks
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> CAST(:vec AS vector)
            LIMIT :k
            """
        ),
        {"vec": vector_str, "k": top_k},
    ).fetchall()

    return [
        RetrievedChunk(
            chunk_id=row.id,
            document_id=row.document_id,
            chunk_index=row.chunk_index,
            page_number=row.page_number,
            text=row.text,
            score=float(row.score),
        )
        for row in rows
    ]
```

---

## API Changes

None — `retrieve()` is an internal service, not directly exposed.

---

## Test Requirements

**`tests/test_retrieval.py`** — replace all stubs with real tests. These are integration tests and require a running Postgres with the migration applied.

- `test_retrieve_returns_empty_when_no_chunks` — query against an empty DB; assert result is `[]`
- `test_retrieve_returns_top_k` — insert N chunks with known embeddings via `SessionLocal`; call `retrieve()` with a matching query vector; assert exactly `top_k` results returned (or fewer if N < top_k)
- `test_retrieve_ordered_by_similarity` — insert chunks with vectors at varying distances from the query; assert results are ordered most-similar first (highest `score` first)
- `test_retrieve_respects_max_top_k_cap` — call with `top_k=999`; assert no more than `MAX_TOP_K` rows returned

**Test fixture pattern** — inserting test chunks directly:
```python
from app.db import SessionLocal
from app.models.document import Document
from app.models.chunk import Chunk

@pytest.fixture
def db_with_chunks():
    with SessionLocal() as session:
        doc = Document(filename="t.txt", content_type="text/plain", sha256="abc", status="ready")
        session.add(doc)
        session.flush()
        chunks = [
            Chunk(document_id=doc.id, chunk_index=i, text=f"chunk {i}",
                  embedding=[float(i)] * 1536)
            for i in range(3)
        ]
        session.add_all(chunks)
        session.commit()
        yield session, doc.id
        # cleanup
        session.delete(doc)
        session.commit()
```

---

## Acceptance Criteria

- [ ] `retrieve()` returns `RetrievedChunk` list ordered by descending cosine similarity
- [ ] Returns `[]` when `chunks` table is empty or has no embeddings
- [ ] `top_k` is capped at `MAX_TOP_K = 20`
- [ ] `score` field is in range `[0, 1]` (cosine similarity)
- [ ] `make test` passes
- [ ] `make lint && make typecheck` passes

---

## Validation Steps

```bash
# After uploading a document:
# (manual — no dedicated endpoint yet, tested via query in Task 07)

make test
make lint
make typecheck
```

---

## Risks

- pgvector requires the `embedding` column to be non-null for distance comparisons — the `WHERE embedding IS NOT NULL` filter handles this
- The `CAST(:vec AS vector)` approach works with SQLAlchemy `text()` and avoids ORM complexities with pgvector types
- Cosine similarity `score = 1 - distance` may be slightly above 1.0 or below 0.0 due to floating-point precision — clamp if needed: `max(0.0, min(1.0, score))`
- Test cleanup: inserted documents/chunks persist in the DB. Use explicit `DELETE` in fixture teardown or accept test data accumulation (acceptable in Phase 1)

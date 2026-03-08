# Task 09 — Complete Test Suite

**Type**: `feature`

**Summary**: Fill any remaining test gaps across the full codebase so that `make test` gives comprehensive coverage of every critical path. By the end of this task, all stub test files are fully implemented, all OpenAI calls are mocked, and the test suite runs clean in CI without a live OpenAI API key.

---

## Context

**Background**: Tasks 02–08 each added targeted tests alongside their implementations. This task audits the full test suite, fills remaining gaps, and ensures the overall suite is reliable and CI-ready. The build guide's Step 10 success criterion is simply "pytest runs successfully" — this task makes that unambiguous.

**Affected components**:
- [x] Backend API (tests only)

---

## Requirements

**Functional — tests must exist and pass for**:
1. `GET /health` — already done in `test_health.py`
2. `POST /documents` — upload, DB record, file on disk, unsupported type → covered in `test_documents.py`
3. Chunking logic — `chunk_text()` size, overlap, sentence boundary, empty input → covered in `test_chunking.py`
4. Text extraction — `.txt`, `.md`, `.pdf` → covered in `test_chunking.py`
5. Embedding service — batching, retry on `openai.APIError` → covered in `test_embedding.py`
6. Retrieval — top-K, ordering, empty DB, cap at MAX_TOP_K → covered in `test_retrieval.py`
7. Generation — prompt construction, LLM call, no-chunks case → covered in `test_generation.py`
8. `POST /query` — full pipeline (mocked), citation fields, excerpt truncation → covered in `test_query.py`
9. `POST /query/stream` — SSE content type, token events, `[DONE]` event → covered in `test_query.py`

**Non-functional**:
- No test makes a real network call (no OpenAI, no external HTTP)
- All tests are independent — no test depends on another test's side-effects
- `make test` completes in under 30 seconds
- `pytest --tb=short` output is clean (no warnings treated as errors)

---

## Implementation Guidelines

**Audit checklist** — for each test file, verify and fill gaps:

### `tests/test_health.py` ✅
- `test_health_returns_ok` — already implemented

### `tests/test_documents.py`
Verify all of these exist and pass:
- `test_upload_txt_returns_201` (status `"ready"` after Task 04)
- `test_upload_saves_file_to_disk`
- `test_upload_creates_db_record`
- `test_upload_unsupported_type_returns_400`
- `test_upload_chunks_have_embeddings` (added in Task 04)
- `test_upload_creates_chunk_rows` (added in Task 03)

Add if missing:
- `test_upload_md_file_accepted` — `.md` files are valid, return 201
- `test_upload_pdf_file_accepted` — `.pdf` files are valid, return 201 (use a minimal real PDF or mock the extraction)

### `tests/test_chunking.py`
Verify all of these exist and pass:
- `test_chunk_text_single_short_string`
- `test_chunk_text_respects_target_size`
- `test_chunk_text_produces_overlap`
- `test_chunk_text_no_empty_chunks`
- `test_extract_text_txt`
- `test_extract_text_md`
- `test_extract_text_pdf`

Add if missing:
- `test_chunk_text_empty_input` — `chunk_text("")` returns `[]`
- `test_extract_text_unsupported_raises` — `extract_text("file.docx")` raises `ValueError`

### `tests/test_embedding.py`
Verify all of these exist and pass:
- `test_embed_chunks_batches_correctly`
- `test_embed_chunks_retries_on_api_error`
- `test_embed_chunks_raises_after_two_failures`
- `test_embed_query_returns_single_vector`

### `tests/test_retrieval.py`
Verify all of these exist and pass:
- `test_retrieve_returns_empty_when_no_chunks`
- `test_retrieve_returns_top_k`
- `test_retrieve_ordered_by_similarity`
- `test_retrieve_respects_max_top_k_cap`

Add if missing:
- `test_retrieve_excludes_chunks_without_embeddings` — insert a chunk with `embedding=None`; assert it does not appear in results

### `tests/test_generation.py`
Verify all of these exist and pass:
- `test_build_user_prompt_includes_chunk_text`
- `test_build_user_prompt_handles_no_chunks`
- `test_generate_answer_calls_chat_completion`
- `test_generate_answer_returns_answer_and_chunks`
- `test_generate_answer_no_chunks_still_calls_llm`

### `tests/test_query.py`
Verify all of these exist and pass:
- `test_query_returns_answer_and_citations`
- `test_query_citation_fields`
- `test_query_excerpt_is_truncated`
- `test_query_empty_chunks_still_returns_answer`
- `test_query_invalid_json_returns_error`
- `test_query_stream_returns_sse_content_type`
- `test_query_stream_yields_tokens`
- `test_query_stream_done_event_is_last`

---

## CI Readiness Checklist

Ensure `make test` passes in an environment with no `.env` file (env vars set via `conftest.py` defaults):

- [ ] `OPENAI_API_KEY=test-key` is set in `conftest.py` before any imports
- [ ] No test imports `openai` directly or calls `get_client()` without a mock
- [ ] All DB-touching tests use the `rag` DB (must be running via `docker compose up postgres -d`)
- [ ] `make migrate` has been run before the test suite

Add a `tests/README.md` documenting how to run the tests locally and what prerequisites are needed (Postgres running, migrations applied).

---

## Acceptance Criteria

- [ ] `pytest tests/ -v` shows all tests collected and passing
- [ ] `pytest tests/ --tb=short` produces no unexpected warnings
- [ ] No test makes a real OpenAI API call
- [ ] `make test` completes in under 30 seconds
- [ ] `make lint && make typecheck` passes with no errors

---

## Validation Steps

```bash
docker compose up postgres -d
make migrate
make test

# Confirm no real API calls are made:
OPENAI_API_KEY=definitely-not-real make test
# Should still pass
```

---

## Risks

- PDF test fixture: `test_extract_text_pdf` needs a real (tiny) PDF file or a mock. Option A: commit a 1-page test PDF to `tests/fixtures/`. Option B: use `pypdf` to programmatically create a minimal PDF in the test. Option A is simpler.
- Integration tests (`test_retrieval.py`) insert real rows into the `rag` DB and may leave residue. Add teardown cleanup or accept it (acceptable for Phase 1).
- If any previous task's tests were skipped or left as stubs, they must be implemented here — do not leave commented-out test code in the final suite.

# Task P3-01 — MCP-Native Query Redesign

**Type**: `redesign`
**Priority**: P0 — implement before any other Phase 3 task

**Summary**: Change `query_documents` in the MCP server to return retrieved chunks as structured context instead of generating an answer server-side. This eliminates the `ANTHROPIC_API_KEY` requirement for MCP use and lets the calling Claude session do the synthesis with its own token budget.

**The REST API (`POST /query`, `POST /query/stream`) is unchanged** — server-side generation stays for non-Claude HTTP clients.

---

## Context

**The problem**: The current `query_documents` MCP tool calls `generation.generate_answer()`, which hits the Anthropic API. This means:
- The MCP server needs `ANTHROPIC_API_KEY` even for users with Claude subscriptions
- Token costs hit the server operator, not the user
- It's architecturally wrong — MCP tools should return data; the AI host synthesises answers

**The fix**: Return chunks. Claude (the calling session) reads the chunks and answers the question naturally in its own context. This is how retrieval tools are meant to work in MCP.

**Affected components**:
- [x] `app/mcp_server.py` — `query_documents` tool return value
- [x] `docs/AGENTS.md` — update arch decisions
- [x] `README.md` — update MCP tools table
- [ ] `app/services/generation.py` — no change (still used by REST API)
- [ ] `app/routers/query.py` — no change

---

## Requirements

**Functional**:

`query_documents` MCP tool new return schema:
```json
{
  "question": "When was the Eiffel Tower built?",
  "chunks": [
    {
      "text": "The Eiffel Tower was built in 1889...",
      "document_id": "3f7a...",
      "filename": "paris-facts.txt",
      "page_number": 1,
      "chunk_index": 0,
      "score": 0.91
    }
  ],
  "chunk_count": 3,
  "hint": "Use the chunks above to answer the question. Cite sources by filename and page."
}
```

The `hint` field guides the calling Claude model on how to use the context. It is a plain string — not an instruction injected into a system prompt, just a suggestion field in the tool result.

**Non-functional**:
- Tool description (the docstring) must be updated to tell Claude what the tool returns and how to use it
- `ANTHROPIC_API_KEY` must be removed from the MCP stdio config in `README.md` and `docs/MCP_TEST_PLAN.md`
- The `~/.claude/settings.json` example in the README must not include `ANTHROPIC_API_KEY`

---

## Implementation Guidelines

**Files to modify**:
- `app/mcp_server.py` — rewrite `query_documents` tool

**Current implementation** (to replace):
```python
@mcp.tool()
async def query_documents(question: str, top_k: int = 5) -> dict[str, Any]:
    """Ask a question and get an answer grounded in your uploaded documents."""
    account_id = get_account_id()

    def _run() -> tuple[str, list[retrieval.RetrievedChunk]]:
        ...
        answer, cited_chunks = generation.generate_answer(question, chunks)
        return answer, cited_chunks

    answer, cited_chunks = await asyncio.to_thread(_run)
    return {"answer": answer, "citations": [...]}
```

**New implementation**:
```python
@mcp.tool()
async def query_documents(question: str, top_k: int = 5) -> dict[str, Any]:
    """Search your knowledge base and return relevant document chunks.

    Returns the most relevant chunks for the given question. Use the chunk
    texts as context to answer the question — cite sources by filename and page.
    Does not generate an answer; the caller synthesises the response.
    """
    account_id = get_account_id()

    def _run() -> list[retrieval.RetrievedChunk]:
        from app.db import SessionLocal
        query_emb = embedding.embed_query(question)
        with SessionLocal() as db:
            return retrieval.retrieve(query_emb, account_id, db, top_k)

    chunks = await asyncio.to_thread(_run)
    return {
        "question": question,
        "chunks": [
            {
                "text": c.text,
                "document_id": str(c.document_id),
                "filename": c.filename,
                "page_number": c.page_number,
                "chunk_index": c.chunk_index,
                "score": round(c.score, 4),
            }
            for c in chunks
        ],
        "chunk_count": len(chunks),
        "hint": "Use the chunks above as context to answer the question. Cite sources by filename and page_number.",
    }
```

Note: `RetrievedChunk` must include `filename` — check `app/services/retrieval.py`. If it doesn't, add it (requires a JOIN to `documents.filename` in the retrieval query).

---

## API Changes

REST API: no changes.

MCP tool `query_documents`: return schema changes as described above.
Update the tool's docstring so MCP clients (and the Claude host) understand what the tool returns.

---

## Test Requirements

Update `tests/test_mcp_server.py`:

- `test_query_documents_returns_chunks` — call `query_documents`, assert response has `chunks`, `question`, `chunk_count` keys; assert `chunks` is a list; assert `"answer"` key is NOT present
- `test_query_documents_chunk_has_required_fields` — assert each chunk has `text`, `document_id`, `filename`, `page_number`, `chunk_index`, `score`
- `test_query_documents_no_anthropic_key_needed` — monkeypatch `ANTHROPIC_API_KEY` to empty string; call `query_documents`; assert it succeeds (no LLM call made)

Remove or update any test that asserts `"answer"` in the `query_documents` response.

---

## Acceptance Criteria

- [ ] `query_documents` returns `{question, chunks, chunk_count, hint}` — no `answer` key
- [ ] `query_documents` does not call `generation.generate_answer()` — verified by mocking and asserting it's never called
- [ ] `query_documents` works with `ANTHROPIC_API_KEY` unset
- [ ] REST `POST /query` still returns `{answer, citations}` — unchanged
- [ ] `README.md` MCP config example does not include `ANTHROPIC_API_KEY`
- [ ] `make test` passes
- [ ] `make lint && make typecheck` passes

---

## Risks

- `RetrievedChunk` dataclass may not include `filename` — the retrieval query joins `chunks` but may not select from `documents`. Check `app/services/retrieval.py` and add the JOIN if needed. This is a small change and must not break the REST query path.
- The MCP test plan (`docs/MCP_TEST_PLAN.md`) references `query_documents` returning an `answer` — update expected results in Test 4 and Test 7.

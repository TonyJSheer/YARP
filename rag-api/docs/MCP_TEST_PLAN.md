# MCP Integration Test Plan

**For**: Claude Code (the AI agent in this session)
**Purpose**: Verify the rag-api MCP server works end-to-end via the stdio transport

---

## Current State

Everything below has already been done — no setup needed before testing:

| Item | Status |
|---|---|
| PostgreSQL running | ✅ `rag-api-postgres-1` healthy on port 5432 |
| Migrations | ✅ at head (0004) |
| `.env` configured | ✅ includes `JWT_SECRET`, `STORAGE_BACKEND=local` (ANTHROPIC_API_KEY not required for MCP) |
| `~/.claude/settings.json` | ✅ `rag-api` MCP server configured for stdio |
| Token generated | ✅ account_id = `tonymac` |
| MCP binary | ✅ `uv run rag-mcp` starts cleanly |

---

## To Activate the MCP Server in This Session

**Claude Code does not hot-reload MCP config.** The `~/.claude/settings.json` was just written. To pick it up:

1. Run `/mcp` in the chat to check current MCP server status
2. If `rag-api` is not listed, **start a new Claude Code session** in this directory — the config is loaded at startup

Once connected, the agent will have four tools available:
- `mcp__rag-api__upload_document`
- `mcp__rag-api__query_documents`
- `mcp__rag-api__list_documents`
- `mcp__rag-api__delete_document`

---

## Test Sequence

Run these in order. Each test builds on the previous one.

---

### Test 1 — List (empty baseline)

**Prompt to agent:**
> Using the rag-api MCP tools, list my documents.

**Expected result:**
```json
{"documents": []}
```

**What it verifies:** MCP server starts, connects to DB, auth token is valid, account scoping works.

---

### Test 2 — Upload a text document

**Prompt to agent:**
> Using the rag-api MCP tools, upload the following content as a file called "test-doc.txt":
> "The capital of France is Paris. The Eiffel Tower was built in 1889 and stands 330 metres tall. Paris has a population of approximately 2.1 million people."

The agent will base64-encode the content and call `upload_document`.

**Expected result:**
```json
{
  "document_id": "<uuid>",
  "status": "ready",
  "chunk_count": 1
}
```

**What it verifies:** Full ingestion pipeline — save to disk, chunk, embed (local sentence-transformers), store vectors in pgvector.

> **Note:** The first upload will be slower than subsequent ones — sentence-transformers downloads the `all-mpnet-base-v2` model (~420MB) on first use. Let it run.

---

### Test 3 — List (document appears)

**Prompt to agent:**
> Using the rag-api MCP tools, list my documents again.

**Expected result:**
```json
{
  "documents": [
    {
      "document_id": "<uuid>",
      "filename": "test-doc.txt",
      "status": "ready",
      "chunk_count": 1
    }
  ]
}
```

**What it verifies:** `list_documents` returns only this account's documents, with accurate chunk count.

---

### Test 4 — Query (grounded answer)

**Prompt to agent:**
> Using the rag-api MCP tools, ask: "When was the Eiffel Tower built and how tall is it?"

**Expected result:** Chunks containing Eiffel Tower facts returned — Claude will synthesise the answer from the chunks.

```json
{
  "question": "When was the Eiffel Tower built and how tall is it?",
  "chunks": [
    {
      "text": "The capital of France is Paris. The Eiffel Tower was built in 1889...",
      "document_id": "<uuid>",
      "filename": "test-doc.txt",
      "page_number": 1,
      "chunk_index": 0,
      "score": 0.9
    }
  ],
  "chunk_count": 1,
  "hint": "Use the chunks above as context to answer the question. Cite sources by filename and page_number."
}
```

**What it verifies:** Embedding of query, pgvector similarity search, chunk retrieval with filename. Claude synthesises the answer from the returned chunks — no server-side LLM call required.

---

### Test 5 — Query (out-of-scope question)

**Prompt to agent:**
> Using the rag-api MCP tools, ask: "What is the population of Tokyo?"

**Expected result:** Answer should say the information is not in the knowledge base. No Tokyo citation.

**What it verifies:** LLM does not hallucinate — it answers "I don't know" when context doesn't support the answer.

---

### Test 6 — Upload a second document

**Prompt to agent:**
> Using the rag-api MCP tools, upload the following content as "cities.txt":
> "Tokyo is the capital of Japan with a population of 13.96 million. It hosted the Summer Olympics in 1964 and 2021."

**Expected result:** New `document_id`, `status: ready`.

---

### Test 7 — Query spans both documents

**Prompt to agent:**
> Using the rag-api MCP tools, ask: "Which city hosted the Olympics and when was the Eiffel Tower built?"

**Expected result:** Chunks from both documents returned — Claude synthesises an answer covering both facts.

```json
{
  "question": "Which city hosted the Olympics and when was the Eiffel Tower built?",
  "chunks": [
    {"filename": "cities.txt", "text": "...hosted the Summer Olympics...", "score": 0.9, "...": "..."},
    {"filename": "test-doc.txt", "text": "...Eiffel Tower was built in 1889...", "score": 0.85, "...": "..."}
  ],
  "chunk_count": 2,
  "hint": "Use the chunks above as context to answer the question. Cite sources by filename and page_number."
}
```

**What it verifies:** Multi-document retrieval works correctly; both filenames appear in chunk results.

---

### Test 8 — Delete a document

**Prompt to agent:**
> Using the rag-api MCP tools, delete the document called "test-doc.txt". You'll need to get its ID from the list first.

**Expected result:** `{"deleted": "<uuid>"}`, no error.

---

### Test 9 — Verify deletion

**Prompt to agent:**
> Using the rag-api MCP tools, ask: "When was the Eiffel Tower built?" — then list documents.

**Expected result:**
- The query answer should now say the information is not available (Eiffel Tower doc is gone)
- List shows only `cities.txt`

**What it verifies:** Deletion removes chunks from pgvector; subsequent queries no longer retrieve deleted content.

---

## Failure Modes to Watch For

| Symptom | Likely cause |
|---|---|
| `rag-api` not in MCP tool list | New session needed — config loads at startup only |
| `MCP_AUTH_TOKEN not set` | Env var missing from `~/.claude/settings.json` |
| `relation "documents" does not exist` | Migrations not applied — run `make migrate` |
| Upload hangs for 2–5 minutes | sentence-transformers model is downloading — wait it out |
| `ANTHROPIC_API_KEY` error | Only affects REST `/query` endpoint — not MCP tools |
| `cannot connect to postgres` | Run `docker compose up postgres -d` from `rag-api/` |

---

## Verify DB State Manually (Optional)

If any test gives unexpected results, check the DB directly:

```bash
cd /Users/tonymac/repos/YARP/rag-api

# Documents
docker compose exec postgres psql -U rag -d rag \
  -c "SELECT id, account_id, filename, status, created_at FROM documents ORDER BY created_at;"

# Chunks per document
docker compose exec postgres psql -U rag -d rag \
  -c "SELECT document_id, count(*) as chunks FROM chunks GROUP BY document_id;"
```

---

## Credentials Reference

| Item | Value |
|---|---|
| account_id | `tonymac` |
| JWT_SECRET | `5036731953eeba7faff2a9149191c8fecc135d6f2129e5c688d04263cd2f8d09` |
| Token | `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0b255bWFjIiwiaWF0IjoxNzczMDUxMTczfQ.OLMLL6zQUd8CFL0DNevA119aW5NOjk0_VsvosptgF04` |
| DB | `postgresql://rag:rag@localhost:5432/rag` |

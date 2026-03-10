# Phase 3 Manual Test Plan

**Scope**: All six P3 tasks — MCP-native query, cloud deployment, async ingestion, hybrid search, reranking, collections + enhanced document management.

**Prerequisites**:
- Local: `make dev` running (postgres + redis via docker compose)
- `make migrate` applied (migrations 0001–0008)
- A JWT token for your test account (see below)
- Claude Code open with `rag-api` MCP server configured in `.mcp.json`

**Generate a test token** (substitute your `JWT_SECRET`):
```bash
cd rag-api
uv run python -c "
import jwt, datetime
secret = '5036731953eeba7faff2a9149191c8fecc135d6f2129e5c688d04263cd2f8d09'
exp = datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=365)
token = jwt.encode({'sub': 'manual-test', 'exp': exp}, secret, algorithm='HS256')
print(token)
"
```

Set `BASE_URL=http://localhost:8000` and `TOKEN=<your-token>` in your shell for the REST examples below.

---

## P3-01 — MCP-Native Query (Return Context, Not Answer)

**Goal**: `query_documents` returns chunks as context; the calling Claude session synthesises the answer using its own token budget. No Anthropic API key required for MCP queries.

### T01-1 — Basic query returns chunks, not a pre-generated answer

1. In Claude Code, type a question that relates to a document you have uploaded.
2. Ask Claude to use the `query_documents` MCP tool directly:
   ```
   Use the query_documents tool to search for "your topic here"
   ```
3. **Verify** the tool returns a dict with `question`, `chunks`, `chunk_count`, and `hint` fields.
4. **Verify** there is NO `answer` field in the response.
5. **Verify** each chunk has: `text`, `document_id`, `filename`, `page_number`, `chunk_index`, `score`.
6. **Verify** Claude synthesises the answer itself using the chunks as context.

### T01-2 — MCP server starts without ANTHROPIC_API_KEY

1. Temporarily remove `ANTHROPIC_API_KEY` from `.mcp.json`.
2. Restart Claude Code / reload MCP servers.
3. Ask Claude to `query_documents`.
4. **Verify** it works — no error about a missing API key.
5. Restore the key (still needed for REST `/query`).

### T01-3 — REST query still generates a server-side answer

```bash
curl -s -X POST $BASE_URL/query \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the main topic of the uploaded document?"}' | jq .
```

**Verify** the response has an `answer` field (full prose) and a `citations` list.

---

## P3-02 — Cloud Deployment (Fly.io + Neon)

**Goal**: The API and MCP server run on Fly.io with Neon for postgres and Tigris/S3 for storage. No local infrastructure needed.

### T02-1 — REST API health check on Fly

```bash
curl -s https://rag-api.fly.dev/health | jq .
```

**Verify** `{"status": "ok"}`.

### T02-2 — Upload and query via REST on cloud

```bash
# Upload a file
curl -s -X POST https://rag-api.fly.dev/documents \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/path/to/test.txt" | jq .

# Note the document_id, then poll until ready
curl -s https://rag-api.fly.dev/documents/<doc_id> \
  -H "Authorization: Bearer $TOKEN" | jq .status

# Query
curl -s -X POST https://rag-api.fly.dev/query \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question": "Summarise this document"}' | jq .answer
```

**Verify** the full pipeline works end-to-end on cloud infrastructure.

### T02-3 — MCP via fly proxy tunnel

```bash
# Open WireGuard tunnel to MCP port (keep this running in background)
fly proxy 8001

# Configure .mcp.json to point at localhost:8001
# "url": "http://localhost:8001/mcp"
```

In Claude Code, reload MCP servers and run a `query_documents` call.

**Verify** the MCP tool works through the tunnel with a JWT Bearer header.

### T02-4 — File stored in Tigris/S3 (not local disk)

```bash
fly ssh console
ls /app/data/uploads/  # should be empty or not exist
```

**Verify** files are not written to disk — they are in Tigris/S3 (`STORAGE_BACKEND=s3`).

---

## P3-03 — Async Ingestion (Redis + Worker)

**Goal**: `upload_document` returns immediately with `status='processing'`; a background worker completes ingestion and sets `status='ready'`.

### T03-1 — Upload returns 'processing' immediately

```bash
time curl -s -X POST $BASE_URL/documents \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/path/to/large.pdf" | jq .
```

**Verify** the response is instant (< 1 second) with `status: "processing"` regardless of file size.

### T03-2 — Status transitions to 'ready'

```bash
DOC_ID=<doc_id from above>
# Poll every 2 seconds
while true; do
  STATUS=$(curl -s $BASE_URL/documents/$DOC_ID -H "Authorization: Bearer $TOKEN" | jq -r .status)
  echo "Status: $STATUS"
  [ "$STATUS" = "ready" ] && break
  sleep 2
done
```

**Verify** status eventually becomes `ready` and `chunk_count` is > 0.

### T03-3 — Worker handles failures gracefully

1. Upload a corrupt file (rename a `.jpg` to `.pdf`):
   ```bash
   cp image.jpg fake.pdf
   curl -s -X POST $BASE_URL/documents \
     -H "Authorization: Bearer $TOKEN" \
     -F "file=@fake.pdf" | jq .
   ```
2. Poll status for the returned `document_id`.
3. **Verify** status becomes `failed` and `error_message` is populated.

### T03-4 — MCP `get_document_status` tool

In Claude Code:
```
Use upload_document to upload this file: [paste base64 of a text file]
Then use get_document_status to check when it's ready.
```

**Verify** the MCP tool correctly reflects `processing` → `ready` transition.

---

## P3-04 — Hybrid Search (BM25 + Vector)

**Goal**: Hybrid mode (default) combines vector similarity and BM25 full-text search via Reciprocal Rank Fusion. Exact keyword matches that vector search would miss are surfaced.

### T04-1 — Hybrid is the default search mode

```bash
curl -s -X POST $BASE_URL/query \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question": "your keyword query"}' | jq .
```

No `search_mode` specified — **verify** the response is successful (uses hybrid by default).

### T04-2 — BM25 finds exact keyword matches

1. Upload a document containing a rare proper noun or technical term (e.g., "Zygomycetes").
2. Wait for `status=ready`.
3. Query with `search_mode: "bm25"`:
   ```bash
   curl -s -X POST $BASE_URL/query \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"question": "Zygomycetes", "search_mode": "bm25"}' | jq .citations
   ```
4. **Verify** the chunk containing "Zygomycetes" is returned.
5. Now try `search_mode: "vector"` with the same query.
6. **Verify** vector mode may return lower-relevance results for rare terms.

### T04-3 — Vector mode finds semantically similar content

1. Upload a document about "automobile fuel efficiency".
2. Query with `search_mode: "vector"` using the phrase "petrol consumption".
3. **Verify** relevant chunks about fuel efficiency are returned even though the exact phrase "petrol consumption" may not appear verbatim.

### T04-4 — Hybrid outperforms single-mode on mixed queries

1. Combine keyword + semantic: query for "Zygomycetes growth temperature optimal".
2. Run in all three modes. Compare results.
3. **Verify** hybrid returns the best combination — the rare keyword chunk plus contextually relevant chunks.

---

## P3-05 — Reranking (Cross-Encoder)

**Goal**: `rerank=True` fetches a wider candidate set (top_k × 4) then re-scores each (question, chunk) pair with a cross-encoder. Results are more relevant but slower.

### T05-1 — Rerank=False (default) is faster

```bash
time curl -s -X POST $BASE_URL/query \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question": "your question", "top_k": 5}' > /dev/null
```

```bash
time curl -s -X POST $BASE_URL/query \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question": "your question", "top_k": 5, "rerank": true}' > /dev/null
```

**Verify** `rerank=true` takes noticeably longer (cross-encoder scoring adds ~0.5–2s).

### T05-2 — Reranked results are ordered differently

1. Use a question where multiple chunks are plausibly relevant.
2. Compare top-3 results with and without rerank.
3. **Verify** the ordering differs — the cross-encoder promotes the most relevant chunk to position 1.

### T05-3 — MCP rerank parameter

In Claude Code:
```
Use query_documents with rerank=true to find information about [topic]
```

**Verify** the tool call completes successfully and returns chunks.

---

## P3-06 — Collections + Enhanced Document Management

### Collections

#### T06-1 — Upload to a named collection (REST)

```bash
curl -s -X POST $BASE_URL/documents \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@legal.txt" \
  -F "collection=legal" | jq .
```

**Verify** 201 response with `document_id`.

```bash
curl -s $BASE_URL/documents \
  -H "Authorization: Bearer $TOKEN" | jq '.documents[] | select(.filename == "legal.txt") | .collection'
```

**Verify** returns `"legal"`.

#### T06-2 — Query scoped to a collection

1. Upload `legal.txt` to collection `legal` and `finance.txt` to collection `finance`.
2. Wait for both to be `ready`.
3. Query scoped to `legal` only:
   ```bash
   curl -s -X POST $BASE_URL/query \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"question": "key terms", "collection": "legal"}' | jq .citations
   ```
4. **Verify** all returned citations are from `legal.txt`, not `finance.txt`.

#### T06-3 — GET /collections

```bash
curl -s $BASE_URL/collections \
  -H "Authorization: Bearer $TOKEN" | jq .
```

**Verify** response:
```json
{
  "collections": [
    {"name": "finance", "document_count": 1},
    {"name": "legal", "document_count": 1}
  ]
}
```

#### T06-4 — MCP list_collections tool

In Claude Code: `Use the list_collections tool`.

**Verify** it returns the same collection names and counts as the REST endpoint.

#### T06-5 — query_documents with collection=None searches all

In Claude Code:
```
Use query_documents without specifying a collection
```

**Verify** results include chunks from multiple collections.

---

### File Formats

#### T06-6 — Upload a .docx file

```bash
# Create a test docx (or use an existing one)
curl -s -X POST $BASE_URL/documents \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@test.docx" | jq .
```

Wait for `status=ready`, then:

```bash
curl -s $BASE_URL/documents/<doc_id> \
  -H "Authorization: Bearer $TOKEN" | jq .chunk_count
```

**Verify** `chunk_count > 0`. Query the document to confirm text was extracted.

> Note: `.doc` (old Word 97 format) is **not** supported — only `.docx`.

#### T06-7 — Upload an .html file

```bash
curl -s -X POST $BASE_URL/documents \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@page.html" | jq .
```

After ingestion, query for content you know is in the `<body>` of the HTML.

**Verify** the returned chunks contain body text but NOT `<nav>`, `<footer>`, `<script>`, or `<style>` content.

#### T06-8 — Upload a .csv file

Create a CSV with headers and ~30 rows, then upload:

```bash
curl -s -X POST $BASE_URL/documents \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@data.csv" | jq .
```

After ingestion, query for a value you know is in a specific row.

**Verify** chunks are formatted as `"column_name: value, ..."` rows grouped in batches of 10.

#### T06-9 — Unsupported extension still returns 400

```bash
curl -s -X POST $BASE_URL/documents \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@archive.zip" | jq .
```

**Verify** `400` with `code: "unsupported_file_type"`.

---

### Metadata

#### T06-10 — Upload with metadata (MCP)

In Claude Code, ask Claude to upload a document with metadata:
```
Use upload_document to upload [base64 content] as "report.txt" with
metadata {"source": "Q4-2025", "author": "alice"}
```

**Verify** the tool call succeeds.

```bash
curl -s $BASE_URL/documents \
  -H "Authorization: Bearer $TOKEN" | jq '.documents[0].metadata'
```

**Verify** `{"source": "Q4-2025", "author": "alice"}` is returned.

#### T06-11 — Upload without metadata returns null

```bash
curl -s $BASE_URL/documents \
  -H "Authorization: Bearer $TOKEN" | jq '.documents[] | select(.metadata == null) | .filename'
```

**Verify** documents uploaded without metadata have `metadata: null` (not missing, not `{}`).

---

### Re-index

#### T06-12 — reindex_document MCP tool

1. Note the current chunk count for a document.
2. In Claude Code:
   ```
   Use reindex_document with document_id "<id>"
   ```
3. **Verify** the tool returns `{"document_id": "...", "chunk_count": N}` where N matches the existing chunk count.
4. **Verify** no error is raised and the document's `status` remains `ready`.

#### T06-13 — reindex_document wrong account returns error

1. Get a `document_id` that belongs to account A.
2. Authenticate as account B.
3. Try to reindex account A's document via account B's token.
4. **Verify** the call returns an error (document not found / 404).

---

## Cross-Cutting: Account Isolation

Run these after any significant upload activity.

### T-ISO-1 — Collections isolated by account

Create two accounts (two JWTs with different `sub` values). Upload to the same collection name ("shared") from each account.

```bash
curl -s $BASE_URL/collections -H "Authorization: Bearer $TOKEN_A" | jq .
curl -s $BASE_URL/collections -H "Authorization: Bearer $TOKEN_B" | jq .
```

**Verify** each account only sees its own collection document counts.

### T-ISO-2 — Queries don't cross account boundaries

Upload a document to account A. Query with account B's token.

**Verify** account B's query returns zero results related to account A's document.

---

## Regression Checklist

Run after all manual tests to confirm no regressions:

```bash
cd rag-api
make test        # 107 tests must pass
make lint        # ruff check + format --check must be clean
make typecheck   # mypy must report "no issues found"
```

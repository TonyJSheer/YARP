# Project Specification — RAG API

Filled-in spec for the RAG API project, derived from `rag_agent_friendly_build.txt`.

---

## 1. Project Overview

**Project Name**: `rag-api`

**Description**: A backend Retrieval-Augmented Generation (RAG) API service. Accepts document uploads, extracts and chunks text, generates and stores embeddings via OpenAI, and answers user questions by retrieving relevant chunks from PostgreSQL (pgvector) and generating a grounded response with citations. Supports streaming answers via Server-Sent Events.

**Primary Goals**:
- Provide a clean, self-contained RAG backend that can be used as a foundation or reference implementation
- Demonstrate real-world AI backend architecture: ingestion pipeline, vector search, LLM generation
- Keep the stack minimal and runnable locally via Docker Compose

---

## 2. Product Type

Select all that apply:
- [x] API platform
- [x] AI service
- [x] Data processing pipeline

---

## 3. Users

**User types**:

| Role | Description |
|---|---|
| `client` | Any HTTP client (curl, frontend app, internal service) that calls the API |

**Permissions model**: No auth required. Open API — this is a developer tool / backend service. API key protection can be added in a later phase if needed.

---

## 4. Core Features

### Feature: Document Upload
- **Description**: Accept file uploads and persist them locally with a database record
- **User actions**: POST /documents with a multipart file
- **System behaviour**: Save file to ./data/uploads, compute sha256, insert record into documents table with status=uploaded

### Feature: Text Extraction + Chunking
- **Description**: Extract text from uploaded files and split into overlapping chunks
- **User actions**: Triggered automatically after upload
- **System behaviour**: Extract text from txt, md, pdf files; split into ~700-token chunks with 80-token overlap, avoid sentence splits; store chunk rows in database

### Feature: Embedding Generation
- **Description**: Generate vector embeddings for each chunk using OpenAI
- **User actions**: Triggered after chunking
- **System behaviour**: Batch calls to OpenAI embeddings API, store 1536-dim vectors in chunks.embedding (pgvector), retry once on failure

### Feature: Vector Retrieval
- **Description**: Find the most relevant chunks for a user query
- **User actions**: Part of the query pipeline
- **System behaviour**: Embed the query, run cosine similarity search via pgvector, return top-K chunks with document id, page number, and text

### Feature: Answer Generation
- **Description**: Generate a grounded answer from retrieved context using an LLM
- **User actions**: Part of the query pipeline
- **System behaviour**: Build a prompt with retrieved chunks as context, call LLM, enforce "answer only from context / cite sources / say I don't know if not found" rules

### Feature: Query Endpoint
- **Description**: Single endpoint exposing the full RAG pipeline
- **User actions**: POST /query with { "question": "...", "top_k": 5 }
- **System behaviour**: Retrieve chunks, generate answer, return { "answer": "...", "citations": [...] }

### Feature: Streaming Query Endpoint
- **Description**: Stream answer tokens as the LLM generates them
- **User actions**: POST /query/stream
- **System behaviour**: SSE response streaming tokens incrementally as they arrive from the LLM

---

## 5. Optional / Phase 2+ Features

- API key authentication
- Async ingestion pipeline with background worker (for large files)
- Document management endpoints (list, delete, re-index)
- Hybrid search (keyword + vector)
- Multi-document filtering by metadata
- Reranking pass before generation

---

## 6. Real-Time Requirements

- [x] Streaming (LLM token streaming via SSE on POST /query/stream)

Details: SSE only on the streaming query endpoint. No persistent connections or live UI updates required.

---

## 7. Data Characteristics

**Primary data types**:
- [x] Relational records (documents, chunks)
- [x] Files / uploads (stored locally)

**Expected data volume (Year 1)**:
- [x] Tiny (< 100 users / documents used in dev/research context)

---

## 8. Background Processing

No background job worker needed for Phase 1. Ingestion (chunking + embedding) runs inline on the upload request, which is acceptable at this scale.

Phase 2 would move ingestion to a Redis-backed worker for large files.

---

## 9. Mobile Support

- [x] Not required

---

## 10. External Integrations

- **OpenAI API**: embeddings (text-embedding-ada-002 or configured model) and chat completions (gpt-4o or configured model)
- No inbound webhooks, no external partner API

---

## 11. Security Requirements

**Authentication**: None for Phase 1 (open API, dev context)

**Special requirements**: Secrets (OPENAI_API_KEY, DATABASE_URL) via environment variables only. No secrets committed to repo.

---

## 12. Performance Expectations

- Single-user / low concurrency workload at launch
- API responses for query under 5s (excluding streaming)
- File uploads up to 50MB
- Embedding generation may take several seconds for large documents — acceptable inline for Phase 1

---

## 13. Constraints

- Must run locally via Docker Compose only — no AWS, no cloud infra in Phase 1
- File storage is local disk (./data/uploads), not S3
- No Redis required in Phase 1
- Use `uv` for Python dependency management
- Use `pyproject.toml`, not requirements.txt

---

## 14. Operational Priorities

1. Development speed
2. Simplicity (minimal moving parts)
3. AI-agent development effectiveness
4. Operational clarity (easy to run, easy to debug)

---

## 15. Delivery Phases

**Phase 1** (MVP — all 10 steps from build guide):
- Base FastAPI project + Docker Compose + Postgres
- Database schema (documents + chunks with pgvector)
- Document upload endpoint
- Text extraction + chunking service
- Embedding generation service
- Vector retrieval service
- LLM answer generation service
- POST /query endpoint
- POST /query/stream SSE endpoint
- Test suite (health, chunking, retrieval, query)

**Phase 2**:
- Async ingestion worker (Redis + worker service)
- API key authentication
- Document management API (list, delete)
- S3 file storage

**Phase 3**:
- Hybrid search
- Reranking
- Multi-document filtering

---

## 16. Open Questions

- Should the embedding model be hardcoded to text-embedding-ada-002 or configurable? → Configurable via OPENAI_EMBED_MODEL env var
- Should chunking happen synchronously on upload or return immediately and process async? → Synchronous for Phase 1 (simpler, acceptable latency at this scale)
- Should we support multiple LLM providers (Anthropic, etc.) or OpenAI only? → OpenAI only in Phase 1; providers/ directory structure allows easy extension

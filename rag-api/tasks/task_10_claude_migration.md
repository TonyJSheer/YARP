# Task 10 — Migrate AI Backend to Claude + sentence-transformers

**Type**: `refactor`

**Summary**: Replace the OpenAI SDK with two new providers: `sentence-transformers` for local embeddings (no API key, 768-dim vectors) and the Anthropic SDK for LLM generation (chat + stream). After this task the system requires only an `ANTHROPIC_API_KEY` to run. A new Alembic migration resizes the `embedding` column from `vector(1536)` to `vector(768)`.

---

## Context

**Background**: All AI calls are isolated in `app/providers/openai_client.py`. Services (`embedding.py`, `generation.py`) call that module exclusively, so the application logic is untouched. This task replaces the provider layer only and adds one DB migration.

**Affected components**:
- [x] Backend API (provider layer + config)
- [x] Database schema (vector dimension change)
- [x] Tests (updated mocks + env vars)

---

## Requirements

**Functional**:
- `embed_chunks(texts)` and `embed_query(text)` use `sentence-transformers` model `all-mpnet-base-v2` (768 dims), loaded lazily on first call
- `chat_completion(system_prompt, user_prompt, model)` calls Anthropic `messages.create` and returns the response text
- `chat_completion_stream(system_prompt, user_prompt, model)` uses Anthropic `messages.stream` and yields token strings
- `[DONE]` is still yielded by `generate_answer_stream()` in `generation.py` (no change needed there)
- Default model falls back to `settings.anthropic_model` (`claude-haiku-4-5-20251001`)
- `POST /documents`, `POST /query`, `POST /query/stream` all work correctly end-to-end

**Non-functional**:
- `OPENAI_API_KEY` is removed from config; `ANTHROPIC_API_KEY` replaces it
- The sentence-transformers model is loaded once and reused (module-level singleton)
- No test makes a real network call

---

## Implementation Guidelines

### 1. Dependencies — `pyproject.toml`

Remove `openai`. Add:
```toml
"anthropic>=0.40.0",
"sentence-transformers>=3.0.0",
```

Run `uv sync` after updating.

### 2. Config — `app/config.py`

Replace OpenAI fields:
```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    database_url: str
    anthropic_api_key: str
    anthropic_model: str = "claude-haiku-4-5-20251001"
    embed_model: str = "all-mpnet-base-v2"
    upload_dir: str = "./data/uploads"
```

### 3. Provider — rename `app/providers/openai_client.py` → `app/providers/ai_client.py`

```python
"""AI provider — sentence-transformers for embeddings, Anthropic for generation."""
from collections.abc import Iterator

import anthropic
from sentence_transformers import SentenceTransformer

from app.config import settings

_embed_model: SentenceTransformer | None = None
_anthropic_client: anthropic.Anthropic | None = None


def get_embed_model() -> SentenceTransformer:
    global _embed_model
    if _embed_model is None:
        _embed_model = SentenceTransformer(settings.embed_model)
    return _embed_model


def get_client() -> anthropic.Anthropic:
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _anthropic_client


def create_embeddings(texts: list[str]) -> list[list[float]]:
    """Generate embeddings using sentence-transformers. Returns one vector per text."""
    model = get_embed_model()
    vectors = model.encode(texts, convert_to_numpy=True)
    return [v.tolist() for v in vectors]


def chat_completion(
    system_prompt: str,
    user_prompt: str,
    model: str | None = None,
) -> str:
    """Generate a chat completion via Anthropic. Returns the response text."""
    message = get_client().messages.create(
        model=model or settings.anthropic_model,
        max_tokens=1024,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return message.content[0].text


def chat_completion_stream(
    system_prompt: str,
    user_prompt: str,
    model: str | None = None,
) -> Iterator[str]:
    """Stream a chat completion via Anthropic. Yields token strings."""
    with get_client().messages.stream(
        model=model or settings.anthropic_model,
        max_tokens=1024,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    ) as stream:
        yield from stream.text_stream
```

### 4. Update imports in services

`app/services/embedding.py` — update the import:
```python
from app.providers import ai_client  # was openai_client
# remove: import openai
```

Update `embed_chunks` — sentence-transformers doesn't raise `openai.APIError`, so remove the retry logic (it's a local model, no network):
```python
def embed_chunks(texts: list[str]) -> list[list[float]]:
    return ai_client.create_embeddings(texts)

def embed_query(text: str) -> list[float]:
    return ai_client.create_embeddings([text])[0]
```

`app/services/generation.py` — update the import:
```python
from app.providers import ai_client  # was openai_client
```
Update calls from `openai_client.chat_completion` → `ai_client.chat_completion` and same for stream.

### 5. Migration — `migrations/versions/0002_resize_embedding_vector.py`

```python
"""Resize embedding column from vector(1536) to vector(768)."""
from alembic import op

revision = "0002"
down_revision = "0001"

def upgrade() -> None:
    # Resets existing embeddings to NULL (dimension mismatch — must re-embed)
    op.execute(
        "ALTER TABLE chunks ALTER COLUMN embedding TYPE vector(768) USING NULL"
    )

def downgrade() -> None:
    op.execute(
        "ALTER TABLE chunks ALTER COLUMN embedding TYPE vector(1536) USING NULL"
    )
```

### 6. Update `app/models/chunk.py`

```python
embedding: Mapped[list[float] | None] = mapped_column(Vector(768), nullable=True)
```

### 7. Update `tests/conftest.py`

Replace `OPENAI_API_KEY` with `ANTHROPIC_API_KEY`:
```python
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
os.environ.setdefault("EMBED_MODEL", "all-mpnet-base-v2")
# Remove OPENAI_API_KEY, OPENAI_EMBED_MODEL, OPENAI_CHAT_MODEL
```

### 8. Update `.env`

```
DATABASE_URL=postgresql://rag:rag@localhost:5432/rag
ANTHROPIC_API_KEY=<real key here>
ANTHROPIC_MODEL=claude-haiku-4-5-20251001
EMBED_MODEL=all-mpnet-base-v2
UPLOAD_DIR=./data/uploads
```

### 9. Update tests

**`tests/test_embedding.py`** — sentence-transformers is local, so:
- Remove retry/API-error tests (no network, no `openai.APIError`)
- Mock `ai_client.create_embeddings` directly instead of `get_client().embeddings.create`
- Keep batching test: `embed_chunks` now calls `create_embeddings` once for all texts (no batching needed — local model handles it)

**`tests/test_generation.py`** — update mock path:
```python
patch("app.providers.ai_client.chat_completion", ...)
```

**`tests/test_documents.py`** — mock path update:
```python
patch("app.services.embedding.embed_chunks", ...)  # unchanged — already patched at service level
```

**`tests/test_query.py`** — mock paths unchanged (already patch at service level).

**`tests/test_embedding.py`** replacement tests:
```python
def test_embed_chunks_returns_vectors() -> None:
    with patch("app.providers.ai_client.create_embeddings", return_value=[[0.1] * 768]):
        result = embed_chunks(["hello"])
    assert len(result) == 1
    assert len(result[0]) == 768

def test_embed_query_returns_single_vector() -> None:
    with patch("app.providers.ai_client.create_embeddings", return_value=[[0.1] * 768]):
        result = embed_query("what is this?")
    assert len(result) == 768
```

---

## API Changes

None — all endpoints unchanged.

---

## Acceptance Criteria

- [ ] `uv sync` succeeds with `anthropic` and `sentence-transformers` in deps, `openai` removed
- [ ] `make migrate` applies migration 0002 (embedding column is now `vector(768)`)
- [ ] `make test` passes — no real API or model calls in unit tests
- [ ] `make lint && make typecheck` passes
- [ ] **Manual integration test** (requires real `ANTHROPIC_API_KEY` in `.env`):
  ```bash
  uv run uvicorn app.main:app --reload
  # Terminal 2:
  echo "The Eiffel Tower is in Paris. It was built in 1889 by Gustave Eiffel and stands 330 metres tall." > /tmp/test.txt
  curl -X POST http://localhost:8000/documents -F "file=@/tmp/test.txt"
  # → {"document_id": "...", "status": "ready"}
  curl -X POST http://localhost:8000/query \
    -H "Content-Type: application/json" \
    -d '{"question": "How tall is the Eiffel Tower?", "top_k": 3}'
  # → {"answer": "...", "citations": [...]}
  curl -N -X POST http://localhost:8000/query/stream \
    -H "Content-Type: application/json" \
    -d '{"question": "Who built the Eiffel Tower?", "top_k": 3}'
  # → SSE tokens ending with data: [DONE]
  ```

---

## Risks

- `sentence-transformers` downloads `all-mpnet-base-v2` (~420MB) on first use — subsequent runs use the cached model at `~/.cache/huggingface/`
- Existing chunk rows have `embedding` values from `vector(1536)` — the migration sets them to NULL. Any documents uploaded before the migration must be re-uploaded to generate new 768-dim embeddings.
- `sentence_transformers.SentenceTransformer` is not annotated for mypy — add `# type: ignore[import-untyped]` as needed.
- The Anthropic `messages.stream` context manager yields from `stream.text_stream` which is a synchronous iterator — compatible with `StreamingResponse` sync generator pattern already in place.

FROM python:3.12-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
# Install dependencies only (no project source yet) — maximises layer cache
RUN uv sync --no-dev --frozen --no-install-project

COPY app/ ./app/
COPY migrations/ ./migrations/
COPY alembic.ini .

# Now install the project package itself (app/ is present)
RUN uv sync --no-dev --frozen

# Pre-download the embedding model at build time so startup is fast in production.
# The model (~420MB) is baked into the image layer — no download on container start.
# Override at build time: docker build --build-arg EMBED_MODEL=all-MiniLM-L6-v2 .
ARG EMBED_MODEL=all-mpnet-base-v2
RUN uv run python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBED_MODEL}')"

# Pre-download the rerank model at build time (~80MB) — no download at runtime.
# Override at build time: docker build --build-arg RERANK_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2 .
ARG RERANK_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
RUN uv run python -c "from sentence_transformers import CrossEncoder; CrossEncoder('${RERANK_MODEL}')"

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

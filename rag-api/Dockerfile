FROM python:3.12-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml .
RUN uv sync --no-dev

COPY app/ ./app/
COPY migrations/ ./migrations/
COPY alembic.ini .

# Pre-download the embedding model at build time so startup is fast in production.
# The model (~420MB) is baked into the image layer — no download on container start.
# Override at build time: docker build --build-arg EMBED_MODEL=all-MiniLM-L6-v2 .
ARG EMBED_MODEL=all-mpnet-base-v2
RUN uv run python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBED_MODEL}')"

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

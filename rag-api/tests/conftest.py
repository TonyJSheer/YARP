import os

import pytest
from fastapi.testclient import TestClient

# Set required env vars before importing app modules (avoids settings validation error)
os.environ.setdefault("DATABASE_URL", "postgresql://rag:rag@localhost:5432/rag")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
os.environ.setdefault("EMBED_MODEL", "all-mpnet-base-v2")
os.environ.setdefault("UPLOAD_DIR", "./data/test_uploads")

from app.main import app  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)

import os

import jwt
import pytest
from fastapi.testclient import TestClient

# Set required env vars before importing app modules (avoids settings validation error)
os.environ.setdefault("DATABASE_URL", "postgresql://rag:rag@localhost:5432/rag")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
os.environ.setdefault("EMBED_MODEL", "all-mpnet-base-v2")
os.environ.setdefault("UPLOAD_DIR", "./data/test_uploads")
os.environ.setdefault("JWT_SECRET", "test-secret")

from app.main import app  # noqa: E402
from app.services import auth  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


TEST_JWT_SECRET = "test-secret"
TEST_JWT_ALGORITHM = "HS256"


@pytest.fixture(autouse=True)
def patch_jwt_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure auth service uses the test secret for every test."""
    monkeypatch.setattr(auth.settings, "jwt_secret", TEST_JWT_SECRET)
    monkeypatch.setattr(auth.settings, "jwt_algorithm", TEST_JWT_ALGORITHM)


@pytest.fixture
def auth_token() -> str:
    """Return a valid JWT for account 'test-account'."""
    return jwt.encode({"sub": "test-account"}, TEST_JWT_SECRET, algorithm=TEST_JWT_ALGORITHM)


@pytest.fixture
def auth_headers(auth_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth_token}"}

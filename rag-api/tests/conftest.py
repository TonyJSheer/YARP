import os
from collections.abc import Generator
from typing import Any

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
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from unittest.mock import patch  # noqa: E402

from app.main import app  # noqa: E402
from app.services import auth  # noqa: E402


@pytest.fixture(autouse=True)
def mock_redis_enqueue() -> Generator[None, None, None]:
    """Patch job_queue.enqueue globally so no test needs a live Redis."""
    with patch("app.services.job_queue.enqueue"):
        yield


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


TEST_JWT_SECRET = "test-secret"
TEST_JWT_ALGORITHM = "HS256"
TEST_ACCOUNT_A = "acct_test_a"
TEST_ACCOUNT_B = "acct_test_b"


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


@pytest.fixture
def token_a() -> str:
    return jwt.encode({"sub": TEST_ACCOUNT_A}, TEST_JWT_SECRET, algorithm=TEST_JWT_ALGORITHM)


@pytest.fixture
def token_b() -> str:
    return jwt.encode({"sub": TEST_ACCOUNT_B}, TEST_JWT_SECRET, algorithm=TEST_JWT_ALGORITHM)


@pytest.fixture
def auth_headers_a(token_a: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token_a}"}


@pytest.fixture
def auth_headers_b(token_b: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token_b}"}


@pytest.fixture
def mock_s3() -> Generator[Any, None, None]:
    """Mocked S3 environment using moto. Yields a boto3 S3 client."""
    from unittest.mock import patch

    from moto import mock_aws

    with patch.dict(
        os.environ,
        {
            "AWS_ACCESS_KEY_ID": "testing",
            "AWS_SECRET_ACCESS_KEY": "testing",
            "AWS_DEFAULT_REGION": "us-east-1",
        },
    ):
        with mock_aws():
            import boto3

            client = boto3.client("s3", region_name="us-east-1")
            client.create_bucket(Bucket="test-rag-bucket")
            yield client


@pytest.fixture
def s3_storage_settings(monkeypatch: pytest.MonkeyPatch, mock_s3: Any) -> None:
    """Override config to use S3 backend with moto."""
    from app.config import settings

    monkeypatch.setattr(settings, "storage_backend", "s3")
    monkeypatch.setattr(settings, "s3_bucket", "test-rag-bucket")
    monkeypatch.setattr(settings, "s3_region", "us-east-1")

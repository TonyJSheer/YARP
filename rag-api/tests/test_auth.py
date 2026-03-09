"""Tests for the JWT auth service (app/services/auth.py)."""

import datetime
from pathlib import Path
from unittest.mock import patch

import jwt
import pytest
from fastapi.testclient import TestClient

from app.services.auth import AuthError, decode_token
from tests.conftest import TEST_JWT_ALGORITHM, TEST_JWT_SECRET

# ---------------------------------------------------------------------------
# Unit tests for decode_token()
# ---------------------------------------------------------------------------


def test_valid_token_returns_account_id() -> None:
    token = jwt.encode({"sub": "acct_001"}, TEST_JWT_SECRET, algorithm=TEST_JWT_ALGORITHM)
    assert decode_token(token) == "acct_001"


def test_expired_token_raises_auth_error() -> None:
    expired_payload = {
        "sub": "acct_001",
        "exp": datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=1),
    }
    token = jwt.encode(expired_payload, TEST_JWT_SECRET, algorithm=TEST_JWT_ALGORITHM)
    with pytest.raises(AuthError, match="token_expired"):
        decode_token(token)


def test_invalid_token_raises_auth_error() -> None:
    with pytest.raises(AuthError, match="invalid_token"):
        decode_token("not.a.valid.jwt")


def test_token_missing_sub_raises_auth_error() -> None:
    token = jwt.encode(
        {"iat": datetime.datetime.now(datetime.UTC)}, TEST_JWT_SECRET, algorithm=TEST_JWT_ALGORITHM
    )
    with pytest.raises(AuthError, match="missing 'sub'"):
        decode_token(token)


# ---------------------------------------------------------------------------
# Integration tests via HTTP
# ---------------------------------------------------------------------------


def test_missing_token_returns_401(client: TestClient) -> None:
    response = client.post(
        "/documents",
        files={"file": ("test.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 401
    error = response.json()["error"]
    assert error["code"] == "unauthorized"


def test_bearer_token_accepted(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    auth_headers: dict[str, str],
) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    with patch(
        "app.services.embedding.embed_chunks",
        side_effect=lambda texts: [[0.1] * 768 for _ in texts],
    ):
        response = client.post(
            "/documents",
            files={"file": ("test.txt", b"hello world", "text/plain")},
            headers=auth_headers,
        )
    assert response.status_code == 201


def test_env_token_accepted(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import settings

    token = jwt.encode({"sub": "acct_env"}, TEST_JWT_SECRET, algorithm=TEST_JWT_ALGORITHM)
    monkeypatch.setenv("MCP_AUTH_TOKEN", token)
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    with patch(
        "app.services.embedding.embed_chunks",
        side_effect=lambda texts: [[0.1] * 768 for _ in texts],
    ):
        response = client.post(
            "/documents",
            files={"file": ("test.txt", b"env token test", "text/plain")},
        )
    assert response.status_code == 201


def test_invalid_token_returns_401(client: TestClient) -> None:
    response = client.post(
        "/documents",
        files={"file": ("test.txt", b"hello", "text/plain")},
        headers={"Authorization": "Bearer garbage.token.value"},
    )
    assert response.status_code == 401
    error = response.json()["error"]
    assert error["code"] == "invalid_token"


def test_expired_token_returns_401_with_token_expired_code(client: TestClient) -> None:
    expired_payload = {
        "sub": "acct_001",
        "exp": datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=1),
    }
    token = jwt.encode(expired_payload, TEST_JWT_SECRET, algorithm=TEST_JWT_ALGORITHM)
    response = client.post(
        "/documents",
        files={"file": ("test.txt", b"hello", "text/plain")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
    error = response.json()["error"]
    assert error["code"] == "token_expired"


def test_health_requires_no_auth(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200

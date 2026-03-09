"""Tests for the StorageService abstraction (local and S3 backends)."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# LocalStorageService
# ---------------------------------------------------------------------------


def test_local_save_creates_file(tmp_path: Path) -> None:
    from app.services.storage import LocalStorageService

    svc = LocalStorageService(str(tmp_path))
    key = svc.save("acct1", "hello.txt", b"hello world")

    saved = Path(svc.get_url(key))
    assert saved.exists()
    assert saved.read_bytes() == b"hello world"


def test_local_save_scopes_by_account_id(tmp_path: Path) -> None:
    from app.services.storage import LocalStorageService

    svc = LocalStorageService(str(tmp_path))
    key_a = svc.save("acct_a", "file.txt", b"data a")
    key_b = svc.save("acct_b", "file.txt", b"data b")

    assert key_a.startswith("acct_a/")
    assert key_b.startswith("acct_b/")
    assert (tmp_path / "acct_a").is_dir()
    assert (tmp_path / "acct_b").is_dir()


def test_local_delete_removes_file(tmp_path: Path) -> None:
    from app.services.storage import LocalStorageService

    svc = LocalStorageService(str(tmp_path))
    key = svc.save("acct1", "todelete.txt", b"bye")

    svc.delete(key)

    assert not Path(svc.get_url(key)).exists()


def test_local_get_url_returns_path(tmp_path: Path) -> None:
    from app.services.storage import LocalStorageService

    svc = LocalStorageService(str(tmp_path))
    key = svc.save("acct1", "url_test.txt", b"content")

    url = svc.get_url(key)
    assert isinstance(url, str)
    assert Path(url).exists()


# ---------------------------------------------------------------------------
# S3StorageService (moto mock)
# ---------------------------------------------------------------------------


@pytest.fixture()
def s3_bucket() -> str:
    return "test-rag-bucket"


@pytest.fixture()
def mock_s3(s3_bucket: str):  # type: ignore[no-untyped-def]
    """Set up a moto-mocked S3 bucket for each test."""
    with (
        patch.dict(
            os.environ,
            {
                "AWS_ACCESS_KEY_ID": "testing",
                "AWS_SECRET_ACCESS_KEY": "testing",
                "AWS_DEFAULT_REGION": "us-east-1",
            },
        ),
    ):
        from moto import mock_aws

        with mock_aws():
            import boto3

            boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=s3_bucket)
            yield


def test_s3_save_uploads_object(mock_s3: None, s3_bucket: str) -> None:
    import boto3

    from app.services.storage import S3StorageService

    svc = S3StorageService(s3_bucket, "us-east-1")
    key = svc.save("acct1", "doc.txt", b"s3 content")

    s3 = boto3.client("s3", region_name="us-east-1")
    response = s3.get_object(Bucket=s3_bucket, Key=key)
    assert response["Body"].read() == b"s3 content"
    assert key.startswith("acct1/")


def test_s3_delete_removes_object(mock_s3: None, s3_bucket: str) -> None:
    import boto3

    from app.services.storage import S3StorageService

    svc = S3StorageService(s3_bucket, "us-east-1")
    key = svc.save("acct1", "to_delete.txt", b"bye s3")
    svc.delete(key)

    s3 = boto3.client("s3", region_name="us-east-1")
    objects = s3.list_objects_v2(Bucket=s3_bucket).get("Contents", [])
    assert not any(obj["Key"] == key for obj in objects)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def test_factory_returns_local_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import settings
    from app.services.storage import LocalStorageService, get_storage_service

    monkeypatch.setattr(settings, "storage_backend", "local")
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))

    svc = get_storage_service()
    assert isinstance(svc, LocalStorageService)


def test_factory_returns_s3_when_configured(
    mock_s3: None,
    s3_bucket: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import settings
    from app.services.storage import S3StorageService, get_storage_service

    monkeypatch.setattr(settings, "storage_backend", "s3")
    monkeypatch.setattr(settings, "s3_bucket", s3_bucket)
    monkeypatch.setattr(settings, "s3_region", "us-east-1")

    svc = get_storage_service()
    assert isinstance(svc, S3StorageService)

"""Storage service — account-scoped file storage with local and S3 backends."""

import uuid
from pathlib import Path
from typing import Protocol


class StorageService(Protocol):
    def save(self, account_id: str, filename: str, data: bytes) -> str: ...
    def delete(self, key: str) -> None: ...
    def get_url(self, key: str) -> str: ...


class LocalStorageService:
    def __init__(self, upload_dir: str) -> None:
        self.base = Path(upload_dir)

    def save(self, account_id: str, filename: str, data: bytes) -> str:
        dest_dir = self.base / account_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        key = f"{account_id}/{uuid.uuid4()}_{filename}"
        (self.base / key).write_bytes(data)
        return key

    def delete(self, key: str) -> None:
        path = self.base / key
        if path.exists():
            path.unlink()

    def get_url(self, key: str) -> str:
        return str(self.base / key)


class S3StorageService:
    def __init__(self, bucket: str, region: str, endpoint_url: str = "") -> None:
        import boto3  # type: ignore[import-untyped]  # lazy import — not needed for local backend

        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            region_name=region,
            endpoint_url=endpoint_url or None,  # None uses default AWS endpoint; set for Fly Tigris
        )

    def save(self, account_id: str, filename: str, data: bytes) -> str:
        key = f"{account_id}/{uuid.uuid4()}_{filename}"
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data)
        return key

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def get_url(self, key: str) -> str:
        return self.client.generate_presigned_url(  # type: ignore[no-any-return]
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=3600,
        )


def get_storage_service() -> StorageService:
    from app.config import settings

    if settings.storage_backend == "s3":
        return S3StorageService(settings.s3_bucket, settings.s3_region, settings.s3_endpoint_url)
    return LocalStorageService(settings.upload_dir)

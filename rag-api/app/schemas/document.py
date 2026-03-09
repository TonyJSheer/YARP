from typing import Any

import msgspec


class DocumentUploadResponse(msgspec.Struct):
    document_id: str
    status: str


class DocumentListItem(msgspec.Struct):
    document_id: str
    filename: str
    status: str
    created_at: str
    chunk_count: int
    collection: str
    metadata: dict[str, Any] | None = None


class DocumentListResponse(msgspec.Struct):
    documents: list[DocumentListItem]


class DocumentDetailResponse(msgspec.Struct):
    document_id: str
    filename: str
    status: str
    created_at: str
    chunk_count: int
    error_message: str | None


class CollectionItem(msgspec.Struct):
    name: str
    document_count: int


class CollectionListResponse(msgspec.Struct):
    collections: list[CollectionItem]

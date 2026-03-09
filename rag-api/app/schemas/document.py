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


class DocumentListResponse(msgspec.Struct):
    documents: list[DocumentListItem]


class DocumentDetailResponse(msgspec.Struct):
    document_id: str
    filename: str
    status: str
    created_at: str
    chunk_count: int
    error_message: str | None

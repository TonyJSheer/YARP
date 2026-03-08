import msgspec


class DocumentUploadResponse(msgspec.Struct):
    document_id: str
    status: str

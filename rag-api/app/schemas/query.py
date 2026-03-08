import msgspec


class Citation(msgspec.Struct):
    document_id: str
    chunk_id: str
    page: int | None
    excerpt: str


class QueryRequest(msgspec.Struct):
    question: str
    top_k: int = 5


class QueryResponse(msgspec.Struct):
    answer: str
    citations: list[Citation]

from collections.abc import Iterator

import msgspec
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.schemas.query import Citation, QueryRequest, QueryResponse
from app.services import embedding, generation, retrieval
from app.services.auth import get_current_account_id

router = APIRouter(prefix="/query", tags=["query"])


@router.post("", response_model=None)
async def query_endpoint(
    request: Request,
    db: Session = Depends(get_db),
    account_id: str = Depends(get_current_account_id),
) -> Response:
    """RAG query — retrieve relevant chunks and generate a grounded answer.

    Request body: {"question": "...", "top_k": 5}
    Response: {"answer": "...", "citations": [...]}
    """
    try:
        req = msgspec.json.decode(await request.body(), type=QueryRequest)
    except (msgspec.DecodeError, msgspec.ValidationError) as exc:
        return JSONResponse(
            status_code=400,
            content={"error": {"code": "invalid_request", "message": str(exc), "field": None}},
        )

    query_vec = embedding.embed_query(req.question)
    chunks = retrieval.retrieve(
        query_vec,
        account_id,
        db,
        top_k=req.top_k,
        search_mode=req.search_mode,
        query_text=req.question,
    )
    answer, cited_chunks = generation.generate_answer(req.question, chunks)

    citations = [
        Citation(
            document_id=str(c.document_id),
            chunk_id=str(c.chunk_id),
            page=c.page_number,
            excerpt=c.text[:200],
        )
        for c in cited_chunks
    ]

    result = QueryResponse(answer=answer, citations=citations)
    return Response(
        content=msgspec.json.encode(result),
        media_type="application/json",
    )


@router.post("/stream")
async def query_stream(
    request: Request,
    db: Session = Depends(get_db),
    account_id: str = Depends(get_current_account_id),
) -> StreamingResponse:
    """RAG query with SSE token streaming.

    Request body: {"question": "...", "top_k": 5}
    Response: text/event-stream — one token per event, final event is [DONE]
    """
    req = msgspec.json.decode(await request.body(), type=QueryRequest)

    query_vec = embedding.embed_query(req.question)
    chunks = retrieval.retrieve(
        query_vec,
        account_id,
        db,
        top_k=req.top_k,
        search_mode=req.search_mode,
        query_text=req.question,
    )

    def event_generator() -> Iterator[str]:
        for token in generation.generate_answer_stream(req.question, chunks):
            yield f"data: {token}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

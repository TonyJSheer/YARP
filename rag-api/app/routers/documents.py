import msgspec
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models.chunk import Chunk
from app.services import document_service, ingestion
from app.services.auth import get_current_account_id
from app.services.storage import get_storage_service

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=None)
async def list_documents(
    account_id: str = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> dict[str, list[dict[str, object]]]:
    items = document_service.list_documents(account_id, db)
    return {"documents": [msgspec.to_builtins(item) for item in items]}


@router.post("", status_code=201, response_model=None)
async def upload_document(
    file: UploadFile,
    db: Session = Depends(get_db),
    account_id: str = Depends(get_current_account_id),
) -> dict[str, str] | JSONResponse:
    """Upload a document for ingestion.

    Accepts a multipart file upload (.txt, .md, .pdf).
    Enqueues the ingestion job and returns document_id immediately
    with status='processing'.
    """
    try:
        doc_id = ingestion.enqueue_ingest(file, account_id, db)
    except ingestion.UnsupportedFileTypeError:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "unsupported_file_type",
                    "message": "Only .txt, .md, and .pdf files are supported",
                    "field": "file",
                }
            },
        )
    return {"document_id": str(doc_id), "status": "processing"}


@router.get("/{document_id}", response_model=None)
async def get_document(
    document_id: str,
    account_id: str = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> dict[str, object] | JSONResponse:
    """Get document detail including current ingestion status."""
    doc = document_service.get_document(document_id, account_id, db)
    if doc is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "not_found",
                    "message": "Document not found",
                    "field": None,
                }
            },
        )

    chunk_count: int = (
        db.query(func.count(Chunk.id)).filter(Chunk.document_id == doc.id).scalar() or 0
    )

    return {
        "document_id": str(doc.id),
        "filename": doc.filename,
        "status": doc.status,
        "created_at": doc.created_at.isoformat(),
        "chunk_count": chunk_count,
        "error_message": doc.error_message,
    }


@router.delete("/{document_id}", status_code=204, response_model=None)
async def delete_document(
    document_id: str,
    account_id: str = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> None:
    storage = get_storage_service()
    try:
        document_service.delete_document(document_id, account_id, db, storage)
    except document_service.DocumentNotFoundError:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "not_found",
                    "message": "Document not found",
                    "field": None,
                }
            },
        )

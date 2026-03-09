import msgspec
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.dependencies import get_db
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
    Runs the full extraction + chunking pipeline and returns document_id
    with status='chunked'.
    """
    try:
        doc_id = ingestion.ingest(file, account_id, db)
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
    except Exception:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "ingestion_failed",
                    "message": "Failed to process the uploaded file.",
                    "field": None,
                }
            },
        )
    return {"document_id": str(doc_id), "status": "ready"}


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

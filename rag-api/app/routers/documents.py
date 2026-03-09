from fastapi import APIRouter, Depends, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.services import ingestion
from app.services.auth import get_current_account_id

router = APIRouter(prefix="/documents", tags=["documents"])


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

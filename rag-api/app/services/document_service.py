"""Document management service — list and delete operations."""

import logging

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.chunk import Chunk
from app.models.document import Document
from app.schemas.document import DocumentListItem
from app.services.storage import StorageService

logger = logging.getLogger(__name__)


class DocumentNotFoundError(Exception):
    pass


def list_documents(account_id: str, db: Session) -> list[DocumentListItem]:
    rows = (
        db.query(Document, func.count(Chunk.id).label("chunk_count"))
        .outerjoin(Chunk, Chunk.document_id == Document.id)
        .filter(Document.account_id == account_id)
        .group_by(Document.id)
        .order_by(Document.created_at.desc())
        .all()
    )
    return [
        DocumentListItem(
            document_id=str(doc.id),
            filename=doc.filename,
            status=doc.status,
            created_at=doc.created_at.isoformat(),
            chunk_count=count,
        )
        for doc, count in rows
    ]


def delete_document(
    document_id: str,
    account_id: str,
    db: Session,
    storage: StorageService,
) -> None:
    doc = (
        db.query(Document)
        .filter(Document.id == document_id, Document.account_id == account_id)
        .first()
    )

    if doc is None:
        raise DocumentNotFoundError()

    storage_key = doc.storage_key

    db.delete(doc)
    db.commit()

    if storage_key:
        try:
            storage.delete(storage_key)
        except Exception:
            logger.error("Failed to delete storage key %s", storage_key)

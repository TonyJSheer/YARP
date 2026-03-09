"""Document management service — list, delete, and re-index operations."""

import logging
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.chunk import Chunk
from app.models.document import Document
from app.schemas.document import CollectionItem, DocumentListItem
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
            collection=doc.collection,
            metadata=doc.doc_metadata,
        )
        for doc, count in rows
    ]


def list_collections(account_id: str, db: Session) -> list[CollectionItem]:
    """Return all collection names and document counts for an account."""
    rows = (
        db.query(Document.collection, func.count(Document.id).label("document_count"))
        .filter(Document.account_id == account_id)
        .group_by(Document.collection)
        .order_by(Document.collection)
        .all()
    )
    return [CollectionItem(name=row.collection, document_count=row.document_count) for row in rows]


def get_document(
    document_id: str,
    account_id: str,
    db: Session,
) -> Document | None:
    """Return the document if it belongs to account_id, else None."""
    return (
        db.query(Document)
        .filter(Document.id == document_id, Document.account_id == account_id)
        .first()
    )


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


def reindex_document(document_id: str, account_id: str, db: Session) -> int:
    """Re-embed all chunks for a document using the current embedding model.

    Returns the number of chunks re-embedded. Raises DocumentNotFoundError if
    the document does not exist or belongs to a different account.
    """
    from app.services import embedding  # avoid circular import

    doc = (
        db.query(Document)
        .filter(Document.id == document_id, Document.account_id == account_id)
        .first()
    )
    if doc is None:
        raise DocumentNotFoundError()

    chunks = db.query(Chunk).filter(Chunk.document_id == doc.id).all()
    if not chunks:
        return 0

    vectors: list[list[float]] = embedding.embed_chunks([c.text for c in chunks])
    for chunk, vector in zip(chunks, vectors):
        chunk.embedding = vector  # type: ignore[assignment]

    db.commit()
    return len(chunks)


def list_documents_raw(account_id: str, db: Session) -> list[dict[str, Any]]:
    """Return documents as plain dicts (used by MCP list_documents tool)."""
    items = list_documents(account_id, db)
    return [
        {
            "document_id": d.document_id,
            "filename": d.filename,
            "status": d.status,
            "created_at": d.created_at,
            "chunk_count": d.chunk_count,
            "collection": d.collection,
            "metadata": d.metadata,
        }
        for d in items
    ]

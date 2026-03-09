"""Ingestion service — orchestrates the full document ingestion pipeline.

Pipeline: save file → extract text → chunk → embed → store chunks
"""

import hashlib
import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.models.chunk import Chunk
from app.models.document import Document
from app.services import chunking, embedding
from app.services.storage import get_storage_service

SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf"}


class UnsupportedFileTypeError(Exception):
    """Raised when an uploaded file has an unsupported extension."""


def save_and_record(file: UploadFile, account_id: str, db: Session) -> tuple[Document, str]:
    """Save an uploaded file via the storage service and create a documents DB record.

    Validates the file extension, saves the file via the configured storage backend,
    computes sha256, and inserts a Document row with status='uploaded'.

    Returns (document, storage_key).
    Raises UnsupportedFileTypeError for non-txt/md/pdf files.
    """
    ext = Path(file.filename or "").suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFileTypeError(ext)

    storage_key, sha256 = _save_file(file, account_id)

    doc = Document(
        account_id=account_id,
        filename=Path(file.filename or "upload").name,
        content_type=file.content_type or "application/octet-stream",
        sha256=sha256,
        storage_key=storage_key,
        status="uploaded",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc, storage_key


def ingest(file: UploadFile, account_id: str, db: Session) -> uuid.UUID:
    """Ingest an uploaded file through the full pipeline.

    1. Save file via storage service and create document record (scoped to account_id)
    2. Set doc.status = 'processing', commit
    3. Extract text from the saved file
    4. Chunk each page's text
    5. Insert Chunk rows (embedding=None)
    6. Generate embeddings for all chunks
    7. Write vectors to Chunk rows, set doc.status = 'ready', commit
    8. Return doc.id
    """
    doc, storage_key = save_and_record(file, account_id, db)

    doc.status = "processing"
    db.commit()

    storage = get_storage_service()

    try:
        file_path = storage.get_url(storage_key)
        texts, page_numbers = chunking.extract_text(file_path)
        chunk_models: list[Chunk] = []
        for page_text, page_num in zip(texts, page_numbers):
            for chunk_str in chunking.chunk_text(page_text):
                chunk_models.append(
                    Chunk(
                        document_id=doc.id,
                        chunk_index=len(chunk_models),
                        page_number=page_num,
                        text=chunk_str,
                        embedding=None,
                    )
                )
        db.add_all(chunk_models)
        db.flush()  # assign IDs before embedding

        vectors = embedding.embed_chunks([c.text for c in chunk_models])
        for chunk, vector in zip(chunk_models, vectors):
            chunk.embedding = vector

        doc.status = "ready"
        db.commit()
    except Exception:
        doc.status = "failed"
        db.commit()
        raise

    return doc.id


def _save_file(file: UploadFile, account_id: str) -> tuple[str, str]:
    """Save uploaded file via the storage service. Returns (storage_key, sha256)."""
    hasher = hashlib.sha256()
    chunks: list[bytes] = []

    while raw := file.file.read(65536):
        hasher.update(raw)
        chunks.append(raw)

    data = b"".join(chunks)
    storage = get_storage_service()
    storage_key = storage.save(account_id, Path(file.filename or "upload").name, data)
    return storage_key, hasher.hexdigest()

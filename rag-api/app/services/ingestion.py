"""Ingestion service — orchestrates the full document ingestion pipeline.

Pipeline: save file → extract text → chunk → embed → store chunks

Async path (used by REST + MCP):
  enqueue_ingest() / enqueue_ingest_from_bytes() — saves file, creates record,
  enqueues job, returns doc.id immediately (status='processing').

Worker path:
  run_ingest_job() — runs extract → chunk → embed → store; called by app.worker.

Sync path (kept for backward-compat / direct test use):
  ingest() / ingest_from_bytes() — runs the full pipeline inline.
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


# ---------------------------------------------------------------------------
# Async fast-path (enqueue)
# ---------------------------------------------------------------------------


def enqueue_ingest(file: UploadFile, account_id: str, db: Session) -> uuid.UUID:
    """Save file, create document record with status='processing', enqueue job.

    Returns document_id immediately — ingestion runs in the background worker.
    Raises UnsupportedFileTypeError for unsupported file extensions.
    """
    from app.services import job_queue

    doc, _ = save_and_record(file, account_id, db)
    doc.status = "processing"
    db.commit()
    job_queue.enqueue(str(doc.id))
    return doc.id


def enqueue_ingest_from_bytes(
    filename: str,
    data: bytes,
    account_id: str,
    db: Session,
) -> uuid.UUID:
    """Save bytes, create document record with status='processing', enqueue job.

    Returns document_id immediately — ingestion runs in the background worker.
    Raises UnsupportedFileTypeError for unsupported file extensions.
    """
    from app.services import job_queue

    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFileTypeError(ext)

    hasher = hashlib.sha256()
    hasher.update(data)
    sha256_hex = hasher.hexdigest()

    storage = get_storage_service()
    storage_key = storage.save(account_id, Path(filename).name, data)

    doc = Document(
        account_id=account_id,
        filename=Path(filename).name,
        content_type="application/octet-stream",
        sha256=sha256_hex,
        storage_key=storage_key,
        status="processing",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    job_queue.enqueue(str(doc.id))
    return doc.id


# ---------------------------------------------------------------------------
# Worker pipeline
# ---------------------------------------------------------------------------


def run_ingest_job(document_id: str, db: Session) -> None:
    """Run the full ingestion pipeline for a queued document.

    Called by the worker process. Sets status='ready' on success,
    status='failed' + error_message on failure.

    Skips silently if the document is already 'ready' (duplicate job guard).
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if doc is None:
        raise ValueError(f"Document {document_id} not found")

    if doc.status == "ready":
        return

    storage = get_storage_service()

    try:
        file_path = storage.get_url(doc.storage_key or "")
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
        db.flush()

        vectors = embedding.embed_chunks([c.text for c in chunk_models])
        for chunk, vector in zip(chunk_models, vectors):
            chunk.embedding = vector

        doc.status = "ready"
        doc.error_message = None
        db.commit()
    except Exception as exc:
        doc.status = "failed"
        doc.error_message = str(exc)
        db.commit()
        raise


# ---------------------------------------------------------------------------
# Sync path (backward compat)
# ---------------------------------------------------------------------------


def ingest(file: UploadFile, account_id: str, db: Session) -> uuid.UUID:
    """Ingest an uploaded file through the full pipeline synchronously.

    Kept for backward-compat and direct test use.
    """
    doc, _ = save_and_record(file, account_id, db)
    doc.status = "processing"
    db.commit()
    run_ingest_job(str(doc.id), db)
    return doc.id


def ingest_from_bytes(
    filename: str,
    data: bytes,
    account_id: str,
    db: Session,
) -> tuple[uuid.UUID, int]:
    """Ingest raw bytes through the full pipeline synchronously.

    Kept for backward-compat. Returns (doc_id, chunk_count).
    """
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFileTypeError(ext)

    hasher = hashlib.sha256()
    hasher.update(data)
    sha256_hex = hasher.hexdigest()

    storage = get_storage_service()
    storage_key = storage.save(account_id, Path(filename).name, data)

    doc = Document(
        account_id=account_id,
        filename=Path(filename).name,
        content_type="application/octet-stream",
        sha256=sha256_hex,
        storage_key=storage_key,
        status="processing",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    run_ingest_job(str(doc.id), db)

    chunk_count = db.query(Chunk).filter(Chunk.document_id == doc.id).count()
    return doc.id, chunk_count


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


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

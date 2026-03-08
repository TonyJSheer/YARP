"""Ingestion service — orchestrates the full document ingestion pipeline.

Pipeline: save file → extract text → chunk → embed → store chunks
"""
import hashlib
import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.models.chunk import Chunk
from app.models.document import Document
from app.services import chunking, embedding

SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf"}


class UnsupportedFileTypeError(Exception):
    """Raised when an uploaded file has an unsupported extension."""


def save_and_record(file: UploadFile, db: Session) -> tuple[Document, Path]:
    """Save an uploaded file to disk and create a documents DB record.

    Validates the file extension, saves the file to UPLOAD_DIR,
    computes sha256, and inserts a Document row with status='uploaded'.

    Returns (document, saved_path).
    Raises UnsupportedFileTypeError for non-txt/md/pdf files.
    """
    ext = Path(file.filename or "").suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFileTypeError(ext)

    path, sha256 = _save_file(file)

    doc = Document(
        filename=Path(file.filename or path.name).name,
        content_type=file.content_type or "application/octet-stream",
        sha256=sha256,
        status="uploaded",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc, path


def ingest(file: UploadFile, db: Session) -> uuid.UUID:
    """Ingest an uploaded file through the full pipeline.

    1. Save file to UPLOAD_DIR and create document record
    2. Set doc.status = 'processing', commit
    3. Extract text from the saved file
    4. Chunk each page's text
    5. Insert Chunk rows (embedding=None)
    6. Generate embeddings for all chunks
    7. Write vectors to Chunk rows, set doc.status = 'ready', commit
    8. Return doc.id
    """
    doc, saved_path = save_and_record(file, db)

    doc.status = "processing"
    db.commit()

    try:
        texts, page_numbers = chunking.extract_text(str(saved_path))
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


def _save_file(file: UploadFile) -> tuple[Path, str]:
    """Save uploaded file to disk. Returns (path, sha256)."""
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    dest = upload_dir / f"{uuid.uuid4()}_{Path(file.filename or 'upload').name}"
    hasher = hashlib.sha256()

    with dest.open("wb") as f:
        while chunk := file.file.read(65536):
            hasher.update(chunk)
            f.write(chunk)

    return dest, hasher.hexdigest()

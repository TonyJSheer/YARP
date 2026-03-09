"""Chunking service — splits text into overlapping chunks.

Strategy:
- Target chunk size: 700 tokens (approximated as ~2800 chars)
- Overlap: 80 tokens (~320 chars)
- Sentence-boundary aware: avoid splitting mid-sentence
"""

import csv
import re
from pathlib import Path

TARGET_TOKENS = 700
OVERLAP_TOKENS = 80

# Approximate chars-per-token ratio for English text
CHARS_PER_TOKEN = 4

TARGET_CHARS = TARGET_TOKENS * CHARS_PER_TOKEN
OVERLAP_CHARS = OVERLAP_TOKENS * CHARS_PER_TOKEN


def extract_text(file_path: str) -> tuple[list[str], list[int | None]]:
    """Extract text from a file. Returns (pages_text, page_numbers).

    Supports: .txt, .md, .pdf, .docx, .html, .csv

    For txt/md/docx/html: returns single page with page_number=None.
    For pdf: returns one entry per page with page_number set (1-indexed).
    For csv: returns one entry per 10-row batch with page_number set (1-indexed).
    Raises ValueError for unsupported file types.
    """
    path = Path(file_path)
    ext = path.suffix.lower()

    if ext in {".txt", ".md"}:
        return _extract_plain(file_path)
    if ext == ".pdf":
        return _extract_pdf(file_path)
    if ext == ".docx":
        return _extract_docx(file_path)
    if ext == ".html":
        return _extract_html(file_path)
    if ext == ".csv":
        return _extract_csv(file_path)

    raise ValueError(f"Unsupported file type: {ext}")


def _extract_plain(file_path: str) -> tuple[list[str], list[int | None]]:
    text = Path(file_path).read_text(encoding="utf-8", errors="replace")
    return [text], [None]


def _extract_pdf(file_path: str) -> tuple[list[str], list[int | None]]:
    from pypdf import PdfReader  # noqa: PLC0415

    reader = PdfReader(str(file_path))
    texts: list[str] = []
    page_numbers: list[int | None] = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if text.strip():
            texts.append(text)
            page_numbers.append(i + 1)
    return texts, page_numbers


def _extract_docx(file_path: str) -> tuple[list[str], list[int | None]]:
    from docx import Document  # noqa: PLC0415

    doc = Document(file_path)
    text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    return [text], [None]


def _extract_html(file_path: str) -> tuple[list[str], list[int | None]]:
    from bs4 import BeautifulSoup  # noqa: PLC0415

    with open(file_path, encoding="utf-8", errors="replace") as f:
        soup = BeautifulSoup(f.read(), "html.parser")

    # Strip boilerplate tags before extracting text
    for tag in soup(["nav", "footer", "script", "style"]):
        tag.decompose()

    text = soup.get_text(separator="\n", strip=True)
    return [text], [None]


def _extract_csv(file_path: str) -> tuple[list[str], list[int | None]]:
    rows: list[str] = []
    with open(file_path, newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(", ".join(f"{k}: {v}" for k, v in row.items()))

    # Batch rows in groups of 10; each batch is one "page"
    batches = ["\n".join(rows[i : i + 10]) for i in range(0, len(rows), 10)]
    if not batches:
        return [], []
    return batches, list(range(1, len(batches) + 1))


def chunk_text(text: str) -> list[str]:
    """Split text into overlapping chunks.

    Returns a list of chunk strings. Each chunk is approximately
    TARGET_TOKENS tokens with OVERLAP_TOKENS overlap.
    Splits at sentence boundaries where possible.
    """
    if not text.strip():
        return []

    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    chunks: list[str] = []
    current: list[str] = []
    current_len: int = 0

    for sentence in sentences:
        s_len = len(sentence)
        if current_len + s_len > TARGET_CHARS and current:
            chunks.append(" ".join(current))
            # Seed next chunk with overlap from the tail of the current chunk
            overlap: list[str] = []
            overlap_len = 0
            for s in reversed(current):
                overlap_len += len(s)
                overlap.insert(0, s)
                if overlap_len >= OVERLAP_CHARS:
                    break
            current, current_len = overlap, sum(len(s) for s in overlap)
        current.append(sentence)
        current_len += s_len

    if current:
        chunks.append(" ".join(current))

    return [c for c in chunks if c.strip()]

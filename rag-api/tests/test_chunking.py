"""Tests for the chunking service (extract_text and chunk_text)."""

from pathlib import Path

import pytest

from app.services.chunking import (
    OVERLAP_CHARS,
    TARGET_CHARS,
    chunk_text,
    extract_text,
)

# ---------------------------------------------------------------------------
# chunk_text tests
# ---------------------------------------------------------------------------


def test_chunk_text_single_short_string() -> None:
    text = "This is a short sentence."
    chunks = chunk_text(text)
    assert chunks == [text]


def test_chunk_text_respects_target_size() -> None:
    # Build text that is definitely longer than TARGET_CHARS.
    sentence = "This is a test sentence with known length. "
    text = sentence * (TARGET_CHARS // len(sentence) + 5)

    chunks = chunk_text(text)
    assert len(chunks) > 1
    # Each chunk (except possibly the last) should be within a reasonable bound.
    for chunk in chunks[:-1]:
        # A chunk can slightly exceed TARGET_CHARS by at most one sentence length.
        assert len(chunk) <= TARGET_CHARS + len(sentence) + 10


def test_chunk_text_produces_overlap() -> None:
    # Create enough text to produce at least 2 chunks.
    sentence = "Overlap sentence number {}. "
    sentences = [sentence.format(i) for i in range(TARGET_CHARS // len(sentence.format(0)) + 10)]
    text = "".join(sentences)

    chunks = chunk_text(text)
    assert len(chunks) >= 2

    # The end of the first chunk should appear at the start of the second chunk.
    first_tail = chunks[0][-OVERLAP_CHARS:]
    second_head = chunks[1][: OVERLAP_CHARS + 20]
    # At least some words from the tail of chunk[0] appear in the head of chunk[1].
    tail_words = set(first_tail.split())
    head_words = set(second_head.split())
    assert tail_words & head_words, "Expected overlap between consecutive chunks"


def test_chunk_text_no_empty_chunks() -> None:
    sentence = "Non-empty sentence. "
    text = sentence * 200
    chunks = chunk_text(text)
    assert all(chunk.strip() for chunk in chunks)
    assert len(chunks) > 0


def test_chunk_text_empty_input() -> None:
    assert chunk_text("") == []
    assert chunk_text("   ") == []


# ---------------------------------------------------------------------------
# extract_text tests
# ---------------------------------------------------------------------------


def test_extract_text_txt(tmp_path: Path) -> None:
    content = "Hello from a text file.\nSecond line here."
    txt_file = tmp_path / "sample.txt"
    txt_file.write_text(content, encoding="utf-8")

    texts, page_numbers = extract_text(str(txt_file))

    assert len(texts) == 1
    assert texts[0] == content
    assert page_numbers == [None]


def test_extract_text_md(tmp_path: Path) -> None:
    content = "# Heading\n\nSome markdown content."
    md_file = tmp_path / "sample.md"
    md_file.write_text(content, encoding="utf-8")

    texts, page_numbers = extract_text(str(md_file))

    assert len(texts) == 1
    assert texts[0] == content
    assert page_numbers == [None]


def test_extract_text_pdf(tmp_path: Path) -> None:
    # Write a minimal valid PDF with embedded text content.
    minimal_pdf = b"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]
  /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj
4 0 obj << /Length 44 >>
stream
BT /F1 12 Tf 100 700 Td (Hello PDF) Tj ET
endstream
endobj
5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj
xref
0 6
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000266 00000 n
0000000360 00000 n
trailer << /Size 6 /Root 1 0 R >>
startxref
441
%%EOF
"""
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(minimal_pdf)

    texts, page_numbers = extract_text(str(pdf_path))

    # pypdf should not crash and should return parallel lists.
    assert isinstance(texts, list)
    assert isinstance(page_numbers, list)
    assert len(texts) == len(page_numbers)
    # All returned page numbers must be 1-indexed integers.
    for pn in page_numbers:
        assert isinstance(pn, int)
        assert pn >= 1


def test_extract_text_unsupported_raises() -> None:
    with pytest.raises(ValueError, match="Unsupported file type"):
        extract_text("document.docx")

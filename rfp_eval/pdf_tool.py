"""Document Tool: extract clean text from an uploaded PDF (PyMuPDF, with pypdf fallback)."""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

from . import config


class PDFExtractionError(Exception):
    """Raised when a PDF cannot be read or contains no usable text."""


@dataclass
class ExtractedDocument:
    text: str
    pages: int
    chars: int
    truncated: bool = False
    warnings: list[str] = field(default_factory=list)


def _extract_pymupdf(data: bytes) -> tuple[list[str], int]:
    import pymupdf  # PyMuPDF >= 1.24 exposes `pymupdf`; older builds expose `fitz`

    with pymupdf.open(stream=data, filetype="pdf") as doc:
        if doc.needs_pass:
            raise PDFExtractionError("The PDF is password-protected.")
        return [page.get_text("text") for page in doc], doc.page_count


def _extract_pypdf(data: bytes) -> tuple[list[str], int]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        raise PDFExtractionError("The PDF is password-protected.")
    return [(p.extract_text() or "") for p in reader.pages], len(reader.pages)


def clean_text(raw: str) -> str:
    text = raw.replace("\u00a0", " ").replace("\u00ad", "")
    text = re.sub(r"-\n(?=[a-z])", "", text)           # re-join hyphenated line breaks
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_text(data: bytes) -> ExtractedDocument:
    """Return cleaned text and metadata, or raise PDFExtractionError with a user-friendly message."""
    if not data or not data.lstrip()[:5] == b"%PDF-":
        raise PDFExtractionError("The file is not a valid PDF.")
    try:
        try:
            page_texts, n_pages = _extract_pymupdf(data)
        except ImportError:
            page_texts, n_pages = _extract_pypdf(data)
    except PDFExtractionError:
        raise
    except Exception as exc:  # corrupt file, unsupported structure, ...
        raise PDFExtractionError(f"The PDF could not be read ({type(exc).__name__}).") from exc

    parts = [f"[Page {i}]\n{clean_text(t)}" for i, t in enumerate(page_texts, start=1) if t.strip()]
    text = "\n\n".join(parts)
    if len(clean_text("".join(page_texts))) < config.MIN_DOC_CHARS:
        raise PDFExtractionError(
            "The PDF contains almost no extractable text (it may be a scanned image). "
            "OCR is out of scope for this project."
        )

    doc = ExtractedDocument(text=text, pages=n_pages, chars=len(text))
    if len(text) > config.MAX_DOC_CHARS:
        doc.text = text[: config.MAX_DOC_CHARS]
        doc.truncated = True
        doc.warnings.append(
            f"Document text truncated from {len(text):,} to {config.MAX_DOC_CHARS:,} characters."
        )
    return doc

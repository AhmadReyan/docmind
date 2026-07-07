"""Text extraction: PDF via pypdf (per page, with OCR fallback for scanned
pages), txt/md as a single unnumbered page."""

import io
import logging
from dataclasses import dataclass

from pypdf import PdfReader
from pypdf._page import PageObject

from app.ingestion.ocr import ocr_image_bytes

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Page:
    text: str
    page_number: int | None  # 1-based for PDFs, None for plain text / markdown


def _sanitize(text: str) -> str:
    # Real-world PDFs (e.g. Stripe receipts) yield NUL bytes from pypdf, which
    # Postgres TEXT rejects ("invalid byte sequence for encoding UTF8: 0x00").
    return text.replace("\x00", "")


def _ocr_page(page: PageObject, page_number: int) -> str:
    """OCR every embedded image on a page (scanned PDFs are image-only)."""
    texts: list[str] = []
    try:
        images = page.images
    except Exception:
        logger.warning("ocr: could not enumerate images on page %d", page_number, exc_info=True)
        return ""
    for image in images:
        text = ocr_image_bytes(image.data)
        if text:
            texts.append(text)
    return "\n".join(texts)


def extract_pages(data: bytes, mime_type: str) -> list[Page]:
    if mime_type == "application/pdf":
        reader = PdfReader(io.BytesIO(data))
        pages: list[Page] = []
        for number, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if not text.strip():
                text = _ocr_page(page, number)
            pages.append(Page(text=_sanitize(text), page_number=number))
        return pages
    # text/plain and text/markdown: decode leniently, keep as one logical page.
    return [Page(text=_sanitize(data.decode("utf-8", errors="replace")), page_number=None)]

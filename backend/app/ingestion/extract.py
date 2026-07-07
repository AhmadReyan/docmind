"""Text extraction: PDF via pypdf (per page), txt/md as a single unnumbered page."""

import io
from dataclasses import dataclass

from pypdf import PdfReader


@dataclass(frozen=True)
class Page:
    text: str
    page_number: int | None  # 1-based for PDFs, None for plain text / markdown


def _sanitize(text: str) -> str:
    # Real-world PDFs (e.g. Stripe receipts) yield NUL bytes from pypdf, which
    # Postgres TEXT rejects ("invalid byte sequence for encoding UTF8: 0x00").
    return text.replace("\x00", "")


def extract_pages(data: bytes, mime_type: str) -> list[Page]:
    if mime_type == "application/pdf":
        reader = PdfReader(io.BytesIO(data))
        return [
            Page(text=_sanitize(page.extract_text() or ""), page_number=number)
            for number, page in enumerate(reader.pages, start=1)
        ]
    # text/plain and text/markdown: decode leniently, keep as one logical page.
    return [Page(text=_sanitize(data.decode("utf-8", errors="replace")), page_number=None)]

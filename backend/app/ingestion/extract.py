"""Text extraction: PDF via pypdf (per page), txt/md as a single unnumbered page."""

import io
from dataclasses import dataclass

from pypdf import PdfReader


@dataclass(frozen=True)
class Page:
    text: str
    page_number: int | None  # 1-based for PDFs, None for plain text / markdown


def extract_pages(data: bytes, mime_type: str) -> list[Page]:
    if mime_type == "application/pdf":
        reader = PdfReader(io.BytesIO(data))
        return [
            Page(text=page.extract_text() or "", page_number=number)
            for number, page in enumerate(reader.pages, start=1)
        ]
    # text/plain and text/markdown: decode leniently, keep as one logical page.
    return [Page(text=data.decode("utf-8", errors="replace"), page_number=None)]

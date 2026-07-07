"""Unit tests for text extraction (txt/md and a handcrafted PDF)."""

from app.ingestion.extract import extract_pages
from tests.utils import build_pdf


def test_plain_text_single_page_no_page_number() -> None:
    pages = extract_pages(b"Hello world.\n\nSecond paragraph.", "text/plain")
    assert len(pages) == 1
    assert pages[0].page_number is None
    assert "Second paragraph." in pages[0].text


def test_markdown_treated_as_text() -> None:
    pages = extract_pages(b"# Title\n\nBody text.", "text/markdown")
    assert len(pages) == 1
    assert pages[0].text.startswith("# Title")


def test_invalid_utf8_replaced_not_raised() -> None:
    pages = extract_pages(b"ok \xff\xfe bytes", "text/plain")
    assert len(pages) == 1
    assert "ok" in pages[0].text


def test_nul_bytes_stripped_from_text() -> None:
    # Postgres TEXT rejects 0x00; real PDFs (e.g. Stripe receipts) contain it.
    pages = extract_pages(b"Invoice U0UJ9K2E\x000001 total \x00$212.00", "text/plain")
    assert "\x00" not in pages[0].text
    assert "U0UJ9K2E0001" in pages[0].text


def test_pdf_pages_extracted_with_page_numbers() -> None:
    data = build_pdf(["Hello from page one", "Hello from page two"])
    pages = extract_pages(data, "application/pdf")
    assert len(pages) == 2
    assert pages[0].page_number == 1
    assert pages[1].page_number == 2
    assert "Hello from page one" in pages[0].text
    assert "Hello from page two" in pages[1].text

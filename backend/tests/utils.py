"""Shared test helpers: a minimal PDF builder and an SSE parser."""

import json
from typing import Any


def build_pdf(pages: list[str]) -> bytes:
    """Assemble a minimal but structurally valid PDF, one text line per page.

    Page text must not contain parentheses or backslashes.
    """
    objects: dict[int, bytes] = {}
    n_pages = len(pages)
    font_num = 3 + 2 * n_pages
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(n_pages))
    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[2] = f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>".encode()
    for i, page_text in enumerate(pages):
        page_num = 3 + 2 * i
        content_num = page_num + 1
        objects[page_num] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Contents {content_num} 0 R "
            f"/Resources << /Font << /F1 {font_num} 0 R >> >> >>"
        ).encode()
        stream = f"BT /F1 12 Tf 72 720 Td ({page_text}) Tj ET".encode()
        objects[content_num] = (
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
        )
    objects[font_num] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"

    out = bytearray(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for num in sorted(objects):
        offsets[num] = len(out)
        out += f"{num} 0 obj\n".encode() + objects[num] + b"\nendobj\n"
    xref_pos = len(out)
    size = len(objects) + 1
    out += f"xref\n0 {size}\n".encode()
    out += b"0000000000 65535 f \n"
    for num in sorted(objects):
        out += f"{offsets[num]:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF".encode()
    return bytes(out)


def parse_sse(body: str) -> list[tuple[str, dict[str, Any]]]:
    """Parse an SSE body into ordered (event_name, parsed_json_data) pairs."""
    events: list[tuple[str, dict[str, Any]]] = []
    for block in body.strip().split("\n\n"):
        event_name: str | None = None
        data_lines: list[str] = []
        for line in block.split("\n"):
            if line.startswith("event: "):
                event_name = line[len("event: ") :]
            elif line.startswith("data: "):
                data_lines.append(line[len("data: ") :])
        if event_name is not None:
            events.append((event_name, json.loads("\n".join(data_lines))))
    return events

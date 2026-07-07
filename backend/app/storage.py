"""File storage abstraction. Local disk today; the Protocol keeps S3 a drop-in later.

Stored object keys follow ``uploads/{user_id}/{document_id}{ext}`` (relative to the
storage root, ``settings.upload_dir``); the key is persisted as ``Document.storage_path``.
"""

import uuid
from pathlib import Path
from typing import BinaryIO, Protocol, cast

from app.config import Settings


def build_storage_path(user_id: uuid.UUID, document_id: uuid.UUID, ext: str) -> str:
    """Object key for an uploaded document, e.g. ``uploads/<uid>/<docid>.pdf``."""
    return f"uploads/{user_id}/{document_id}{ext}"


class Storage(Protocol):
    def save(self, path: str, data: bytes) -> None: ...

    def open(self, path: str) -> BinaryIO: ...

    def delete(self, path: str) -> None: ...


class LocalDiskStorage:
    """Stores objects as plain files under a root directory."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)

    def _resolve(self, path: str) -> Path:
        full = (self._root / path).resolve()
        root = self._root.resolve()
        if not full.is_relative_to(root):
            raise ValueError(f"Storage path escapes root: {path}")
        return full

    def save(self, path: str, data: bytes) -> None:
        full = self._resolve(path)
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(data)

    def open(self, path: str) -> BinaryIO:
        return cast(BinaryIO, self._resolve(path).open("rb"))

    def delete(self, path: str) -> None:
        self._resolve(path).unlink(missing_ok=True)


def get_storage(settings: Settings) -> Storage:
    return LocalDiskStorage(settings.upload_dir)

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

DocumentStatus = Literal["pending", "processing", "ready", "failed"]


class DocumentOut(BaseModel):
    id: uuid.UUID
    title: str
    filename: str
    mime_type: str
    size_bytes: int
    status: DocumentStatus
    error_message: str | None
    page_count: int | None
    chunk_count: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ChunkOut(BaseModel):
    id: uuid.UUID
    chunk_index: int
    content: str
    page_number: int | None
    token_count: int

    model_config = {"from_attributes": True}

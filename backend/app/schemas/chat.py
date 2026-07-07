import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ConversationOut(BaseModel):
    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class Source(BaseModel):
    """A citation frozen onto an assistant message; `index` matches [n] markers."""

    index: int
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    page_number: int | None
    snippet: str
    score: float


class MessageOut(BaseModel):
    id: uuid.UUID
    role: Literal["user", "assistant"]
    content: str
    sources: list[Source] | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class ProvidersOut(BaseModel):
    llm: str
    embedding: str


class HealthOut(BaseModel):
    status: Literal["ok"]
    db: bool
    redis: bool
    providers: ProvidersOut

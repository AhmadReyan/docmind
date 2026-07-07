"""Conversation CRUD and the SSE chat endpoint.

SSE event order (docs/api-contract.md): ``sources`` (once) -> ``token`` (0+) ->
``done`` (once, after the assistant message is persisted). Any mid-stream failure
emits a terminal ``error`` event instead. Rate limiting is checked before anything
else and returns a plain (non-SSE) 429 JSON response.
"""

import json
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, status
from fastapi.responses import StreamingResponse
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select, update
from sqlalchemy.orm import selectinload

from app.api.deps import ArqPoolDep, CurrentUser, PaginationDep, SessionDep, SettingsDep
from app.core import rate_limit
from app.core.errors import ApiError
from app.db import get_session_factory
from app.models import Conversation, Message
from app.providers.base import ChatMessage, get_embedding_provider, get_llm_provider
from app.rag.pipeline import SourcesEvent, answer_question
from app.schemas.chat import ConversationDetail, ConversationOut, SendMessageRequest
from app.schemas.common import Page

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/conversations", tags=["chat"])

DEFAULT_CONVERSATION_TITLE = "New conversation"
TITLE_MAX_LENGTH = 60


def _not_found() -> ApiError:
    return ApiError(status.HTTP_404_NOT_FOUND, "Conversation not found", "not_found")


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _get_owned_conversation(
    session: SessionDep, user_id: uuid.UUID, conversation_id: uuid.UUID
) -> Conversation:
    conversation = await session.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.user_id == user_id
        )
    )
    if conversation is None:
        raise _not_found()
    return conversation


@router.post("", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
async def create_conversation(user: CurrentUser, session: SessionDep) -> Conversation:
    conversation = Conversation(user_id=user.id)
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return conversation


@router.get("", response_model=Page[ConversationOut])
async def list_conversations(
    user: CurrentUser, session: SessionDep, pagination: PaginationDep
) -> Page[ConversationOut]:
    total = await session.scalar(
        select(func.count()).select_from(Conversation).where(Conversation.user_id == user.id)
    )
    rows = await session.scalars(
        select(Conversation)
        .where(Conversation.user_id == user.id)
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
        .limit(pagination.limit)
        .offset(pagination.offset)
    )
    return Page(items=[ConversationOut.model_validate(c) for c in rows], total=total or 0)


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> Conversation:
    conversation = await session.scalar(
        select(Conversation)
        .where(Conversation.id == conversation_id, Conversation.user_id == user.id)
        .options(selectinload(Conversation.messages))
    )
    if conversation is None:
        raise _not_found()
    return conversation


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> None:
    conversation = await _get_owned_conversation(session, user.id, conversation_id)
    await session.execute(sa_delete(Conversation).where(Conversation.id == conversation.id))
    await session.commit()


@router.post("/{conversation_id}/messages")
async def send_message(
    conversation_id: uuid.UUID,
    payload: SendMessageRequest,
    user: CurrentUser,
    session: SessionDep,
    settings: SettingsDep,
    pool: ArqPoolDep,
) -> StreamingResponse:
    allowed = await rate_limit.hit(
        pool, rate_limit.chat_key(user.id), settings.chat_rate_limit_per_minute, 60
    )
    if not allowed:
        raise ApiError(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many chat messages, slow down",
            "rate_limited",
        )
    conversation = await _get_owned_conversation(session, user.id, conversation_id)

    # History for the prompt = messages that existed before this user message.
    prior = await session.scalars(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.asc(), Message.id.asc())
    )
    history: list[ChatMessage] = [
        {"role": "user" if m.role == "user" else "assistant", "content": m.content} for m in prior
    ]

    question = payload.content
    user_message = Message(conversation_id=conversation.id, role="user", content=question)
    session.add(user_message)
    await session.commit()

    was_default_title = conversation.title == DEFAULT_CONVERSATION_TITLE
    current_title = conversation.title
    user_id = user.id
    convo_id = conversation.id

    async def event_stream() -> AsyncIterator[str]:
        # The request-scoped session may be closed once the handler returns,
        # so the stream owns a fresh session for retrieval and persistence.
        try:
            embedding_provider = get_embedding_provider(settings)
            llm_provider = get_llm_provider(settings)
            deltas: list[str] = []
            sources_json: list[dict[str, Any]] = []
            async with get_session_factory()() as stream_session:
                events = answer_question(
                    stream_session,
                    user_id,
                    question,
                    history,
                    embedding_provider=embedding_provider,
                    llm_provider=llm_provider,
                )
                async for event in events:
                    if isinstance(event, SourcesEvent):
                        sources_json = [s.model_dump(mode="json") for s in event.sources]
                        yield _sse("sources", {"sources": sources_json})
                    else:
                        deltas.append(event.delta)
                        yield _sse("token", {"delta": event.delta})

                assistant_message = Message(
                    conversation_id=convo_id,
                    role="assistant",
                    content="".join(deltas),
                    sources=sources_json,
                )
                stream_session.add(assistant_message)
                title = question.strip()[:TITLE_MAX_LENGTH] if was_default_title else current_title
                await stream_session.execute(
                    update(Conversation)
                    .where(Conversation.id == convo_id)
                    .values(title=title, updated_at=func.now())
                )
                await stream_session.commit()
                await stream_session.refresh(assistant_message)
                yield _sse(
                    "done",
                    {"message_id": str(assistant_message.id), "conversation_title": title},
                )
        except Exception:
            logger.exception("Chat stream failed for conversation %s", convo_id)
            yield _sse(
                "error",
                {"detail": "Failed to generate a response", "code": "internal_error"},
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

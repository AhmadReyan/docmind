"""OpenAI-compatible providers (also serves Ollama / LM Studio / vLLM via base_url)."""

from collections.abc import AsyncIterator
from typing import Any, cast

from openai import AsyncOpenAI

from app.config import Settings
from app.models import EMBEDDING_DIM
from app.providers.base import ChatMessage


class OpenAIEmbeddingProvider:
    name = "openai"
    dimension = EMBEDDING_DIM

    def __init__(self, settings: Settings) -> None:
        self._client = AsyncOpenAI(
            api_key=settings.openai_api_key, base_url=settings.openai_base_url
        )
        self._model = settings.openai_embedding_model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        response = await self._client.embeddings.create(
            model=self._model,
            input=texts,
            dimensions=self.dimension,
        )
        ordered = sorted(response.data, key=lambda item: item.index)
        return [list(item.embedding) for item in ordered]


class OpenAILLMProvider:
    name = "openai"

    def __init__(self, settings: Settings) -> None:
        self._client = AsyncOpenAI(
            api_key=settings.openai_api_key, base_url=settings.openai_base_url
        )
        self._model = settings.openai_llm_model

    async def generate_stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> AsyncIterator[str]:
        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=cast(Any, messages),
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

"""Anthropic LLM provider (generation only — Anthropic has no embeddings API)."""

from collections.abc import AsyncIterator
from typing import Any, cast

from anthropic import AsyncAnthropic

from app.config import Settings
from app.providers.base import ChatMessage


class AnthropicLLMProvider:
    name = "anthropic"

    def __init__(self, settings: Settings) -> None:
        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._model = settings.anthropic_model

    async def generate_stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> AsyncIterator[str]:
        # Anthropic takes the system prompt as a top-level param, not a message.
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        chat = [
            {"role": m["role"], "content": m["content"]} for m in messages if m["role"] != "system"
        ]
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": chat,
        }
        if system:
            kwargs["system"] = system
        async with self._client.messages.stream(**cast(Any, kwargs)) as stream:
            async for delta in stream.text_stream:
                yield delta

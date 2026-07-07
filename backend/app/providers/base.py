"""Provider abstraction: the pluggable heart of DocMind.

Embedding and LLM providers are selected *independently* via settings
(`EMBEDDING_PROVIDER`, `LLM_PROVIDER`) because they are independent concerns —
e.g. Anthropic offers generation but no embeddings API.

All embedding providers must produce vectors of ``app.models.EMBEDDING_DIM``
(384) so the pgvector column and index never need migrating when providers
are switched.
"""

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Literal, Protocol, TypedDict, runtime_checkable

if TYPE_CHECKING:
    from app.config import Settings


class ChatMessage(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str


@runtime_checkable
class EmbeddingProvider(Protocol):
    name: str
    dimension: int  # must equal app.models.EMBEDDING_DIM

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts into unit-normalized vectors."""
        ...


@runtime_checkable
class LLMProvider(Protocol):
    name: str

    def generate_stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> AsyncIterator[str]:
        """Yield text deltas for the assistant response."""
        ...


def get_embedding_provider(settings: "Settings") -> EmbeddingProvider:
    """Registry keyed by settings.embedding_provider: 'local' | 'openai' | 'hash'."""
    if settings.embedding_provider == "local":
        from app.providers.local import LocalEmbeddingProvider

        return LocalEmbeddingProvider()
    if settings.embedding_provider == "openai":
        from app.providers.openai_compat import OpenAIEmbeddingProvider

        return OpenAIEmbeddingProvider(settings)
    if settings.embedding_provider == "hash":
        from app.providers.hashing import HashEmbeddingProvider

        return HashEmbeddingProvider()
    raise ValueError(f"Unknown embedding provider: {settings.embedding_provider}")


def get_llm_provider(settings: "Settings") -> LLMProvider:
    """Registry keyed by settings.llm_provider: 'local' | 'openai' | 'anthropic'."""
    if settings.llm_provider == "local":
        from app.providers.local import LocalLLMProvider

        return LocalLLMProvider()
    if settings.llm_provider == "openai":
        from app.providers.openai_compat import OpenAILLMProvider

        return OpenAILLMProvider(settings)
    if settings.llm_provider == "anthropic":
        from app.providers.anthropic_provider import AnthropicLLMProvider

        return AnthropicLLMProvider(settings)
    raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")

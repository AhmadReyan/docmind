"""Deterministic hash-based embeddings for tests and offline eval.

Each token maps to a pseudo-random 384-dim vector seeded from its SHA-256 digest;
text embeddings are the L2-normalized mean of the token vectors. Fully deterministic
across processes and platforms (Mersenne Twister sequences are stable given a seed),
dependency-free, and instant — but semantically meaningless beyond token overlap.
"""

import hashlib
import math
import random
import re

from app.models import EMBEDDING_DIM

_TOKEN_RE = re.compile(r"[a-z0-9]+")


class HashEmbeddingProvider:
    name = "hash"
    dimension = EMBEDDING_DIM

    def __init__(self) -> None:
        self._token_cache: dict[str, list[float]] = {}

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_text(text) for text in texts]

    def _embed_text(self, text: str) -> list[float]:
        tokens = _TOKEN_RE.findall(text.lower()) or [""]
        acc = [0.0] * self.dimension
        for token in tokens:
            vec = self._token_vector(token)
            for i, value in enumerate(vec):
                acc[i] += value
        mean = [value / len(tokens) for value in acc]
        return _l2_normalize(mean)

    def _token_vector(self, token: str) -> list[float]:
        cached = self._token_cache.get(token)
        if cached is not None:
            return cached
        seed = int.from_bytes(hashlib.sha256(token.encode("utf-8")).digest(), "big")
        rng = random.Random(seed)
        vec = [rng.uniform(-1.0, 1.0) for _ in range(self.dimension)]
        self._token_cache[token] = vec
        return vec


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vec))
    if norm == 0.0:
        unit = [0.0] * len(vec)
        unit[0] = 1.0
        return unit
    return [value / norm for value in vec]

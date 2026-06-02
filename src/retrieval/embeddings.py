"""Embedding provider interfaces for retrieval experiments."""

from __future__ import annotations

import hashlib
import math
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(slots=True)
class EmbeddingConfig:
    """Configuration envelope for an embedding provider."""

    provider_name: str
    model_name: str
    batch_size: int = 32
    extra_options: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class EmbeddingRequest:
    """Texts to embed for indexing or querying."""

    texts: list[str]
    input_type: Literal["document", "query"] = "document"


class EmbeddingProvider(ABC):
    """Abstract interface for embedding generation."""

    @abstractmethod
    def embed(self, request: EmbeddingRequest) -> list[list[float]]:
        """Embed the supplied texts.

        TODO:
        - integrate provider-specific API calls
        - batch request execution
        - capture provider and model metadata for experiment logging
        """


class HashingEmbeddingProvider(EmbeddingProvider):
    """Dependency-free token hashing embedding provider.

    This is a local baseline provider. It is not a semantic model, but it keeps
    the embedding-index path executable before external model providers are
    wired in.
    """

    def __init__(self, config: EmbeddingConfig | None = None) -> None:
        self.config = config or EmbeddingConfig(
            provider_name="hashing",
            model_name="hashing-token-v1",
        )
        self.dimensions = int(self.config.extra_options.get("dimensions", 256))
        if self.dimensions <= 0:
            raise ValueError("embedding dimensions must be greater than zero")

    def embed(self, request: EmbeddingRequest) -> list[list[float]]:
        """Embed texts using normalized feature hashing."""

        return [
            _normalize(_hash_tokens(_tokenize(text), self.dimensions))
            for text in request.texts
        ]


def create_embedding_provider(config: EmbeddingConfig) -> EmbeddingProvider:
    """Create a concrete embedding provider from config."""

    if config.provider_name in {"hashing", "local_hashing"}:
        return HashingEmbeddingProvider(config)
    raise ValueError(f"Unsupported embedding provider: {config.provider_name}")


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[0-9A-Za-z가-힣]+", text.lower())


def _hash_tokens(tokens: list[str], dimensions: int) -> list[float]:
    vector = [0.0] * dimensions
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:8], "big") % dimensions
        sign = 1.0 if digest[8] % 2 == 0 else -1.0
        vector[index] += sign
    return vector


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]

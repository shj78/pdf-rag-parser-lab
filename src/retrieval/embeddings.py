"""Embedding provider interfaces for retrieval experiments."""

from __future__ import annotations

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

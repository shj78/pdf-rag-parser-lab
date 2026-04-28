"""Vector index interfaces for retrieval experiments."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from src.schemas import Chunk, RetrievalResult


@dataclass(slots=True)
class IndexConfig:
    """Configuration envelope for a vector index backend."""

    backend_name: str
    namespace: str = "default"
    extra_options: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SearchRequest:
    """Query-time input for a vector index search."""

    query_id: str
    query_text: str
    top_k: int = 10
    filters: dict[str, Any] = field(default_factory=dict)


class VectorIndex(ABC):
    """Abstract interface for index build and search operations."""

    @abstractmethod
    def build(self, chunks: list[Chunk]) -> None:
        """Build or refresh the search index from chunks.

        TODO:
        - define how chunk embeddings are persisted
        - choose backend-specific storage behavior
        - log index build metadata for experiments
        """

    @abstractmethod
    def search(self, request: SearchRequest) -> list[RetrievalResult]:
        """Return initial retrieval results before reranking.

        TODO:
        - map backend scores into the shared RetrievalResult schema
        - preserve chunk metadata required for analysis
        """

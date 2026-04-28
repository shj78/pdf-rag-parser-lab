"""Common adapter contracts for reranker integration."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from src.schemas import RetrievalResult


@dataclass(slots=True)
class RerankRequest:
    """Inputs required to rerank a retrieved candidate set."""

    query_id: str
    query_text: str
    candidates: list[RetrievalResult]
    top_k: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseRerankerAdapter(ABC):
    """Abstract bridge interface for reranking components."""

    @abstractmethod
    def rerank(self, request: RerankRequest) -> list[RetrievalResult]:
        """Rerank retrieved candidates using an existing reranker.

        TODO:
        - bridge into an existing reranker process, endpoint, or module
        - map reranker outputs back into RetrievalResult
        - keep original retrieval scores for comparison
        """

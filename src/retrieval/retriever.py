"""Retriever orchestration scaffold."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.schemas import RetrievalResult

from .embeddings import EmbeddingProvider
from .index import VectorIndex
from .reranker_adapter import BaseRerankerAdapter


@dataclass(slots=True)
class RetrievalPipelineConfig:
    """Configuration envelope for retrieval and reranking flow."""

    top_k_before_rerank: int = 20
    top_k_after_rerank: int = 10
    enable_reranker: bool = True
    metadata_filters: dict[str, Any] = field(default_factory=dict)


class Retriever:
    """High-level retrieval orchestrator.

    The retriever owns pipeline composition only. Concrete embedding, index, and
    reranker behavior are delegated to their respective adapters.
    """

    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        vector_index: VectorIndex,
        reranker: BaseRerankerAdapter | None = None,
        config: RetrievalPipelineConfig | None = None,
    ) -> None:
        self.embedding_provider = embedding_provider
        self.vector_index = vector_index
        self.reranker = reranker
        self.config = config or RetrievalPipelineConfig()

    def retrieve(self, query_id: str, query_text: str) -> list[RetrievalResult]:
        """Retrieve and optionally rerank results for a query.

        TODO:
        - embed the query with the configured provider
        - execute vector search
        - optionally rerank with the existing bridge
        - emit run metadata for evaluation
        """

        _ = (query_id, query_text)
        _ = (
            self.embedding_provider,
            self.vector_index,
            self.reranker,
            self.config,
        )
        raise NotImplementedError("TODO: implement retrieval orchestration.")

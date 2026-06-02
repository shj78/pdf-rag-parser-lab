"""Retriever orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from src.schemas import RetrievalResult

from .embeddings import EmbeddingProvider
from .index import SearchRequest, VectorIndex
from .reranker_adapter import BaseRerankerAdapter, RerankRequest


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
        vector_index: VectorIndex,
        embedding_provider: EmbeddingProvider | None = None,
        reranker: BaseRerankerAdapter | None = None,
        config: RetrievalPipelineConfig | None = None,
    ) -> None:
        self.embedding_provider = embedding_provider
        self.vector_index = vector_index
        self.reranker = reranker
        self.config = config or RetrievalPipelineConfig()
        _validate_config(self.config)

    def retrieve(self, query_id: str, query_text: str) -> list[RetrievalResult]:
        """Retrieve and optionally rerank results for a query."""

        initial_results = self.vector_index.search(
            SearchRequest(
                query_id=query_id,
                query_text=query_text,
                top_k=self.config.top_k_before_rerank,
                filters=dict(self.config.metadata_filters),
            )
        )

        if self.config.enable_reranker and self.reranker is not None:
            reranked_results = self.reranker.rerank(
                RerankRequest(
                    query_id=query_id,
                    query_text=query_text,
                    candidates=initial_results,
                    top_k=self.config.top_k_after_rerank,
                    metadata={
                        "top_k_before_rerank": self.config.top_k_before_rerank,
                        "metadata_filters": dict(self.config.metadata_filters),
                    },
                )
            )
            return _finalize_results(
                reranked_results,
                top_k=self.config.top_k_after_rerank,
                stage="reranked",
            )

        return _finalize_results(
            initial_results,
            top_k=self.config.top_k_after_rerank,
            stage="initial",
        )


def _validate_config(config: RetrievalPipelineConfig) -> None:
    if config.top_k_before_rerank <= 0:
        raise ValueError("top_k_before_rerank must be greater than zero")
    if config.top_k_after_rerank <= 0:
        raise ValueError("top_k_after_rerank must be greater than zero")


def _finalize_results(
    results: list[RetrievalResult],
    *,
    top_k: int,
    stage: str,
) -> list[RetrievalResult]:
    finalized: list[RetrievalResult] = []
    for rank, result in enumerate(results[:top_k], start=1):
        finalized.append(
            replace(
                result,
                rank=rank,
                metadata={
                    **result.metadata,
                    "initial_rank": result.rank,
                    "retriever_stage": stage,
                },
            )
        )
    return finalized

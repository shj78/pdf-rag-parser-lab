from __future__ import annotations

from src.retrieval.index import SearchRequest, VectorIndex
from src.retrieval.reranker_adapter import BaseRerankerAdapter, RerankRequest
from src.retrieval.retriever import RetrievalPipelineConfig, Retriever
from src.schemas import Chunk, RetrievalResult


def test_retriever_searches_index_with_pipeline_config() -> None:
    index = _StubIndex(
        [
            _result("q1", "chunk-1", rank=1, chunk_type="table"),
            _result("q1", "chunk-2", rank=2, chunk_type="text"),
        ]
    )
    retriever = Retriever(
        vector_index=index,
        config=RetrievalPipelineConfig(
            top_k_before_rerank=5,
            top_k_after_rerank=1,
            enable_reranker=False,
            metadata_filters={"chunk_type": "table"},
        ),
    )

    results = retriever.retrieve("q1", "지급일")

    assert index.last_request == SearchRequest(
        query_id="q1",
        query_text="지급일",
        top_k=5,
        filters={"chunk_type": "table"},
    )
    assert len(results) == 1
    assert results[0].chunk_id == "chunk-1"
    assert results[0].rank == 1
    assert results[0].metadata["initial_rank"] == 1
    assert results[0].metadata["retriever_stage"] == "initial"


def test_retriever_reranks_when_enabled() -> None:
    index = _StubIndex(
        [
            _result("q1", "chunk-1", rank=1),
            _result("q1", "chunk-2", rank=2),
        ]
    )
    reranker = _ReverseReranker()
    retriever = Retriever(
        vector_index=index,
        reranker=reranker,
        config=RetrievalPipelineConfig(
            top_k_before_rerank=2,
            top_k_after_rerank=1,
            enable_reranker=True,
        ),
    )

    results = retriever.retrieve("q1", "지급일")

    assert reranker.last_request is not None
    assert reranker.last_request.top_k == 1
    assert [candidate.chunk_id for candidate in reranker.last_request.candidates] == [
        "chunk-1",
        "chunk-2",
    ]
    assert results[0].chunk_id == "chunk-2"
    assert results[0].rank == 1
    assert results[0].metadata["initial_rank"] == 2
    assert results[0].metadata["retriever_stage"] == "reranked"


def test_retriever_skips_missing_reranker_even_when_enabled() -> None:
    index = _StubIndex([_result("q1", "chunk-1", rank=1)])
    retriever = Retriever(
        vector_index=index,
        config=RetrievalPipelineConfig(enable_reranker=True),
    )

    results = retriever.retrieve("q1", "지급일")

    assert results[0].metadata["retriever_stage"] == "initial"


class _StubIndex(VectorIndex):
    def __init__(self, results: list[RetrievalResult]) -> None:
        self.results = results
        self.last_request: SearchRequest | None = None

    def build(self, chunks: list[Chunk]) -> None:
        self.chunks = chunks

    def search(self, request: SearchRequest) -> list[RetrievalResult]:
        self.last_request = request
        return self.results[: request.top_k]


class _ReverseReranker(BaseRerankerAdapter):
    def __init__(self) -> None:
        self.last_request: RerankRequest | None = None

    def rerank(self, request: RerankRequest) -> list[RetrievalResult]:
        self.last_request = request
        return list(reversed(request.candidates))[: request.top_k]


def _result(
    query_id: str,
    chunk_id: str,
    *,
    rank: int,
    chunk_type: str = "text",
) -> RetrievalResult:
    return RetrievalResult(
        query_id=query_id,
        chunk_id=chunk_id,
        document_id="doc",
        parser_name="mineru",
        rank=rank,
        metadata={"chunk_type": chunk_type},
    )

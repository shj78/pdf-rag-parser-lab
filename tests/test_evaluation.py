from __future__ import annotations

import pytest

from src.evaluation.evaluator import EvaluatorConfig, RetrievalEvaluator
from src.evaluation.metrics import compute_ndcg_at_k
from src.evaluation.schemas import (
    EvaluationQuery,
    QueryEvaluationInput,
    RelevanceLabel,
)
from src.schemas import RetrievalResult


def test_compute_ndcg_at_k_returns_one_for_ideal_ranking() -> None:
    evaluation_input = _query_input(
        retrieved_results=[
            _result("q1", "chunk-1", rank=1),
            _result("q1", "chunk-2", rank=2),
            _result("q1", "chunk-3", rank=3),
        ],
        relevance_labels=[
            RelevanceLabel(query_id="q1", chunk_id="chunk-1", grade=3),
            RelevanceLabel(query_id="q1", chunk_id="chunk-2", grade=2),
            RelevanceLabel(query_id="q1", chunk_id="chunk-3", grade=1),
        ],
    )

    assert compute_ndcg_at_k(evaluation_input, 3) == pytest.approx(1.0)


def test_compute_ndcg_at_k_sorts_by_rank_and_treats_missing_labels_as_zero() -> None:
    evaluation_input = _query_input(
        retrieved_results=[
            _result("q1", "irrelevant", rank=3),
            _result("q1", "chunk-2", rank=1),
            _result("q1", "chunk-1", rank=2),
        ],
        relevance_labels=[
            RelevanceLabel(query_id="q1", chunk_id="chunk-1", grade=3),
            RelevanceLabel(query_id="q1", chunk_id="chunk-2", grade=2),
        ],
    )

    score = compute_ndcg_at_k(evaluation_input, 2)

    assert 0.0 < score < 1.0


def test_compute_ndcg_at_k_requires_positive_k() -> None:
    with pytest.raises(ValueError, match="k must be greater than zero"):
        compute_ndcg_at_k(_query_input(), 0)


def test_retrieval_evaluator_returns_query_scores_and_run_average() -> None:
    evaluator = RetrievalEvaluator(EvaluatorConfig(k_values=[2]))
    perfect_query = _query_input(
        query_id="q1",
        retrieved_results=[
            _result("q1", "chunk-1", rank=1),
            _result("q1", "chunk-2", rank=2),
        ],
        relevance_labels=[
            RelevanceLabel(query_id="q1", chunk_id="chunk-1", grade=2),
            RelevanceLabel(query_id="q1", chunk_id="chunk-2", grade=1),
        ],
    )
    missed_query = _query_input(
        query_id="q2",
        retrieved_results=[_result("q2", "chunk-x", rank=1)],
        relevance_labels=[RelevanceLabel(query_id="q2", chunk_id="chunk-y", grade=2)],
    )

    assert evaluator.evaluate_query(perfect_query)["ndcg@2"] == pytest.approx(1.0)

    result = evaluator.evaluate_run(
        run_id="run-1",
        parser_name="mineru",
        chunker_name="fixed_size",
        queries=[perfect_query, missed_query],
    )

    assert result.metadata["query_count"] == 2
    assert set(result.query_results) == {"q1", "q2"}
    assert result.scores[0].metric_name == "ndcg"
    assert result.scores[0].k == 2
    assert result.scores[0].value == pytest.approx(0.5)


def _query_input(
    *,
    query_id: str = "q1",
    retrieved_results: list[RetrievalResult] | None = None,
    relevance_labels: list[RelevanceLabel] | None = None,
) -> QueryEvaluationInput:
    return QueryEvaluationInput(
        query=EvaluationQuery(query_id=query_id, query_text="청년수당 지급일"),
        retrieved_results=retrieved_results or [],
        relevance_labels=relevance_labels or [],
        parser_name="mineru",
        chunker_name="fixed_size",
    )


def _result(query_id: str, chunk_id: str, *, rank: int) -> RetrievalResult:
    return RetrievalResult(
        query_id=query_id,
        chunk_id=chunk_id,
        document_id="doc",
        parser_name="mineru",
        rank=rank,
    )

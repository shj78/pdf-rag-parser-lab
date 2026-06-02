"""Metric functions for retrieval evaluation."""

from __future__ import annotations

import math

from src.schemas import RetrievalResult

from .schemas import QueryEvaluationInput


def compute_ndcg_at_k(evaluation_input: QueryEvaluationInput, k: int) -> float:
    """Compute NDCG@k for a single query.

    Relevance labels are treated as graded labels. Missing labels are
    considered non-relevant and contribute zero gain.
    """

    if k <= 0:
        raise ValueError("k must be greater than zero")

    label_by_chunk = _labels_for_query(evaluation_input)
    ranked_results = _ranked_results(evaluation_input)
    dcg = _discounted_cumulative_gain(
        [label_by_chunk.get(result.chunk_id, 0) for result in ranked_results[:k]]
    )
    idcg = _discounted_cumulative_gain(
        sorted(label_by_chunk.values(), reverse=True)[:k]
    )
    if idcg == 0:
        return 0.0
    return dcg / idcg


def _labels_for_query(evaluation_input: QueryEvaluationInput) -> dict[str, int]:
    labels: dict[str, int] = {}
    for label in evaluation_input.relevance_labels:
        if label.query_id != evaluation_input.query.query_id:
            continue
        labels[label.chunk_id] = max(labels.get(label.chunk_id, 0), max(label.grade, 0))
    return labels


def _ranked_results(evaluation_input: QueryEvaluationInput) -> list[RetrievalResult]:
    return [
        result
        for _, result in sorted(
            enumerate(evaluation_input.retrieved_results),
            key=lambda item: (
                item[1].rank if item[1].rank is not None else item[0] + 1,
                item[0],
            ),
        )
    ]


def _discounted_cumulative_gain(grades: list[int]) -> float:
    return sum(_gain(grade) / math.log2(index + 2) for index, grade in enumerate(grades))


def _gain(grade: int) -> float:
    return float((2**grade) - 1)

"""Metric function signatures for retrieval evaluation."""

from __future__ import annotations

from .schemas import QueryEvaluationInput


def compute_ndcg_at_k(evaluation_input: QueryEvaluationInput, k: int) -> float:
    """Compute NDCG@k for a single query.

    TODO:
    - define gain mapping for graded relevance labels
    - align ranking inputs with RetrievalResult ordering
    - document handling for missing labels
    """

    raise NotImplementedError("TODO: implement NDCG@k calculation.")

"""Evaluator orchestration scaffold for retrieval experiments."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .schemas import EvaluationResult, QueryEvaluationInput


@dataclass(slots=True)
class EvaluatorConfig:
    """Configuration envelope for evaluation runs."""

    metric_names: list[str] = field(default_factory=lambda: ["ndcg"])
    k_values: list[int] = field(default_factory=lambda: [5, 10])
    extra_options: dict[str, Any] = field(default_factory=dict)


class RetrievalEvaluator:
    """Evaluate retrieval results against relevance labels."""

    def __init__(self, config: EvaluatorConfig | None = None) -> None:
        self.config = config or EvaluatorConfig()

    def evaluate_query(self, evaluation_input: QueryEvaluationInput) -> dict[str, float]:
        """Evaluate a single query.

        TODO:
        - dispatch to metric functions such as NDCG@k
        - keep metric outputs aligned with query identifiers
        """

        raise NotImplementedError("TODO: implement per-query evaluation.")

    def evaluate_run(
        self,
        run_id: str,
        parser_name: str,
        chunker_name: str,
        queries: list[QueryEvaluationInput],
    ) -> EvaluationResult:
        """Aggregate evaluation across multiple queries.

        TODO:
        - collect per-query scores
        - aggregate run-level summary metrics
        - persist evaluation metadata for experiment comparison
        """

        raise NotImplementedError("TODO: implement run-level evaluation.")

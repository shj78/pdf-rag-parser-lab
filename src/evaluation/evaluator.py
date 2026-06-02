"""Evaluator orchestration for retrieval experiments."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .metrics import compute_ndcg_at_k
from .schemas import EvaluationResult, MetricScore, QueryEvaluationInput


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
        """Evaluate a single query."""

        scores: dict[str, float] = {}
        for metric_name in self.config.metric_names:
            if metric_name != "ndcg":
                raise ValueError(f"Unsupported metric: {metric_name}")
            for k in self.config.k_values:
                scores[f"ndcg@{k}"] = compute_ndcg_at_k(evaluation_input, k)
        return scores

    def evaluate_run(
        self,
        run_id: str,
        parser_name: str,
        chunker_name: str,
        queries: list[QueryEvaluationInput],
    ) -> EvaluationResult:
        """Aggregate evaluation across multiple queries."""

        query_results: dict[str, list[MetricScore]] = {}
        aggregate_values: dict[str, list[float]] = {}

        for query_input in queries:
            query_scores = self.evaluate_query(query_input)
            metric_scores: list[MetricScore] = []
            for metric_key, value in query_scores.items():
                metric_name, k = _split_metric_key(metric_key)
                metric_scores.append(
                    MetricScore(metric_name=metric_name, value=value, k=k)
                )
                aggregate_values.setdefault(metric_key, []).append(value)
            query_results[query_input.query.query_id] = metric_scores

        aggregate_scores = [
            MetricScore(
                metric_name=metric_name,
                value=sum(values) / len(values),
                k=k,
                notes=f"mean over {len(values)} queries",
            )
            for metric_key, values in sorted(aggregate_values.items())
            for metric_name, k in [_split_metric_key(metric_key)]
        ]

        return EvaluationResult(
            run_id=run_id,
            parser_name=parser_name,
            chunker_name=chunker_name,
            scores=aggregate_scores,
            query_results=query_results,
            metadata={
                "query_count": len(queries),
                "metric_names": list(self.config.metric_names),
                "k_values": list(self.config.k_values),
                **self.config.extra_options,
            },
        )


def _split_metric_key(metric_key: str) -> tuple[str, int | None]:
    if "@" not in metric_key:
        return metric_key, None
    metric_name, k_value = metric_key.split("@", 1)
    return metric_name, int(k_value)

"""Schemas for relevance labels and evaluation outputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.schemas import RetrievalResult


@dataclass(slots=True)
class RelevanceLabel:
    """Ground-truth style label for a query and chunk pair."""

    query_id: str
    chunk_id: str
    grade: int
    rationale: str | None = None
    source: str = "manual"


@dataclass(slots=True)
class EvaluationQuery:
    """Evaluation query definition."""

    query_id: str
    query_text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class QueryEvaluationInput:
    """Single-query evaluation payload."""

    query: EvaluationQuery
    retrieved_results: list[RetrievalResult]
    relevance_labels: list[RelevanceLabel]
    parser_name: str
    chunker_name: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MetricScore:
    """Named metric output."""

    metric_name: str
    value: float
    k: int | None = None
    notes: str | None = None


@dataclass(slots=True)
class EvaluationResult:
    """Aggregate evaluation result for a run."""

    run_id: str
    parser_name: str
    chunker_name: str
    scores: list[MetricScore] = field(default_factory=list)
    query_results: dict[str, list[MetricScore]] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

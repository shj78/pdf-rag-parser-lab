"""Bridge to an existing reranker implementation."""

from __future__ import annotations

import importlib
import inspect
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from src.schemas import RetrievalResult

from .reranker_adapter import BaseRerankerAdapter, RerankRequest


@dataclass(slots=True)
class ExistingRerankerBridgeConfig:
    """Configuration for connecting to the already existing reranker."""

    mode: str = "python_module"
    endpoint: str | None = None
    entrypoint: str | None = None
    timeout_seconds: int = 30
    extra_options: dict[str, Any] = field(default_factory=dict)


class ExistingRerankerBridge(BaseRerankerAdapter):
    """Adapter reserved for the existing reranker integration path.

    This scaffold is intentionally not a new reranker. Its role is to preserve a
    stable contract around whatever reranker implementation already exists.
    """

    def __init__(self, config: ExistingRerankerBridgeConfig) -> None:
        self.config = config

    def rerank(self, request: RerankRequest) -> list[RetrievalResult]:
        """Rerank candidates using the configured bridge target."""

        if self.config.mode != "python_module":
            raise ValueError(f"Unsupported reranker bridge mode: {self.config.mode}")
        if not request.candidates:
            return []

        reranker = _load_entrypoint(self.config.entrypoint)
        payloads = [_candidate_to_payload(candidate) for candidate in request.candidates]
        raw_results = _call_reranker(
            reranker,
            request=request,
            payloads=payloads,
            extra_options=self.config.extra_options,
        )
        return _normalize_results(
            raw_results,
            request=request,
            stage_metadata={
                "reranker_bridge_mode": self.config.mode,
                "reranker_entrypoint": self.config.entrypoint,
            },
        )

    def healthcheck(self) -> None:
        """Validate that the bridge target is importable."""

        if self.config.mode != "python_module":
            raise ValueError(f"Unsupported reranker bridge mode: {self.config.mode}")
        _load_entrypoint(self.config.entrypoint)


def _load_entrypoint(entrypoint: str | None) -> Callable[..., Any]:
    if not entrypoint or ":" not in entrypoint:
        raise ValueError("python_module mode requires entrypoint='module:function'")
    module_name, function_name = entrypoint.split(":", 1)
    module = importlib.import_module(module_name)
    target = getattr(module, function_name, None)
    if not callable(target):
        raise ValueError(f"Reranker entrypoint is not callable: {entrypoint}")
    return target


def _candidate_to_payload(candidate: RetrievalResult) -> dict[str, Any]:
    content = (
        candidate.metadata.get("content")
        or candidate.metadata.get("text")
        or candidate.metadata.get("text_preview")
        or ""
    )
    return {
        "chunk_id": candidate.chunk_id,
        "id": candidate.chunk_id,
        "document_id": candidate.document_id,
        "parser_name": candidate.parser_name,
        "content": str(content),
        "score": candidate.score,
        "similarity": candidate.score,
        "rank": candidate.rank,
        "page_number": candidate.page_number,
        "rerank_score": candidate.rerank_score,
        "metadata": dict(candidate.metadata),
    }


def _call_reranker(
    reranker: Callable[..., Any],
    *,
    request: RerankRequest,
    payloads: list[dict[str, Any]],
    extra_options: dict[str, Any],
) -> Sequence[Any]:
    top_k = request.top_k or len(payloads)
    kwargs = {"top_n": top_k, **extra_options}
    signature = inspect.signature(reranker)
    accepted_kwargs = {
        key: value for key, value in kwargs.items() if key in signature.parameters
    }

    try:
        return reranker(request.query_text, payloads, **accepted_kwargs)
    except TypeError as exc:
        if accepted_kwargs:
            return reranker(request.query_text, payloads)
        raise exc


def _normalize_results(
    raw_results: Sequence[Any],
    *,
    request: RerankRequest,
    stage_metadata: dict[str, Any],
) -> list[RetrievalResult]:
    by_chunk_id = {candidate.chunk_id: candidate for candidate in request.candidates}
    by_content = {
        str(_candidate_to_payload(candidate)["content"]): candidate
        for candidate in request.candidates
    }
    normalized: list[RetrievalResult] = []
    for index, raw_result in enumerate(raw_results, start=1):
        result = _normalize_single_result(
            raw_result,
            by_chunk_id=by_chunk_id,
            by_content=by_content,
            rank=index,
            stage_metadata=stage_metadata,
        )
        normalized.append(result)
        if request.top_k is not None and len(normalized) >= request.top_k:
            break
    return normalized


def _normalize_single_result(
    raw_result: Any,
    *,
    by_chunk_id: dict[str, RetrievalResult],
    by_content: dict[str, RetrievalResult],
    rank: int,
    stage_metadata: dict[str, Any],
) -> RetrievalResult:
    if isinstance(raw_result, RetrievalResult):
        return replace(
            raw_result,
            rank=rank,
            metadata={**raw_result.metadata, **stage_metadata},
        )

    if isinstance(raw_result, str):
        candidate = by_chunk_id.get(raw_result)
        if candidate is None:
            raise ValueError(f"Reranker returned unknown chunk_id: {raw_result}")
        return _reranked_candidate(candidate, rank=rank, stage_metadata=stage_metadata)

    if isinstance(raw_result, dict):
        chunk_id = raw_result.get("chunk_id") or raw_result.get("id")
        candidate = by_chunk_id.get(str(chunk_id)) if chunk_id else None
        if candidate is None and raw_result.get("content") is not None:
            candidate = by_content.get(str(raw_result["content"]))
        if candidate is None:
            raise ValueError("Reranker returned a result that cannot be mapped to a candidate")
        rerank_score = raw_result.get("rerank_score", raw_result.get("score"))
        return _reranked_candidate(
            candidate,
            rank=rank,
            rerank_score=float(rerank_score) if rerank_score is not None else None,
            extra_metadata=raw_result.get("metadata", {}),
            stage_metadata=stage_metadata,
        )

    raise ValueError(f"Unsupported reranker result type: {type(raw_result).__name__}")


def _reranked_candidate(
    candidate: RetrievalResult,
    *,
    rank: int,
    rerank_score: float | None = None,
    extra_metadata: dict[str, Any] | None = None,
    stage_metadata: dict[str, Any],
) -> RetrievalResult:
    return replace(
        candidate,
        rank=rank,
        rerank_score=rerank_score if rerank_score is not None else candidate.rerank_score,
        metadata={
            **candidate.metadata,
            **(extra_metadata or {}),
            **stage_metadata,
        },
    )

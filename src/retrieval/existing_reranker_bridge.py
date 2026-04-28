"""Placeholder bridge to an existing reranker implementation."""

from __future__ import annotations

from dataclasses import dataclass, field
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
        """Rerank candidates using the existing reranker integration.

        TODO:
        - support bridge modes such as module call or HTTP endpoint
        - normalize return shape into RetrievalResult
        - capture bridge metadata for experiment logging
        """

        raise NotImplementedError(
            "TODO: connect this adapter to the existing reranker."
        )

    def healthcheck(self) -> None:
        """Validate that the bridge target is reachable.

        TODO: implement environment or endpoint validation for the existing
        reranker dependency.
        """

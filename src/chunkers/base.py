"""Abstract interfaces for chunking strategies."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

from src.schemas import Chunk, ParsedDocument


@dataclass(slots=True)
class ChunkerConfig:
    """Configuration envelope for a chunking strategy."""

    chunker_name: str
    target_chunk_size: int | None = None
    overlap: int | None = None
    parser_name: str | None = None
    extra_options: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ChunkingRequest:
    """Input contract for chunking a parsed document."""

    document: ParsedDocument
    config: ChunkerConfig


class BaseChunker(ABC):
    """Base contract for chunking strategies.

    Chunk implementations should populate metadata that allows later comparison
    across parser choices and retrieval runs.
    """

    name: ClassVar[str] = "base"

    @abstractmethod
    def chunk(self, request: ChunkingRequest) -> list[Chunk]:
        """Split a parsed document into retrieval-ready chunks.

        Required chunk metadata fields:
        - chunk_id
        - document_id
        - page_number
        - chunk_type
        - section_title
        - heading_path
        - parser_name

        TODO:
        - implement strategy-specific chunk segmentation
        - preserve traceability to source blocks
        - emit consistent metadata across chunkers
        """


__all__ = ["BaseChunker", "ChunkerConfig", "ChunkingRequest"]

"""Placeholder markdown-heading-aware chunker."""

from __future__ import annotations

from src.schemas import Chunk

from .base import BaseChunker, ChunkingRequest


class MarkdownHeadingChunker(BaseChunker):
    """Chunker placeholder for heading-preserving chunk creation."""

    name = "markdown_heading"

    def chunk(self, request: ChunkingRequest) -> list[Chunk]:
        """Create chunks aligned to heading structure when available.

        TODO:
        - define how parser outputs become heading-aware intermediate text
        - preserve heading_path and section_title metadata
        - compare retrieval impact against fixed-size chunking
        """

        raise NotImplementedError(
            "TODO: implement the markdown-heading chunker."
        )

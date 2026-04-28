"""Placeholder fixed-size chunker."""

from __future__ import annotations

from src.schemas import Chunk

from .base import BaseChunker, ChunkingRequest


class FixedSizeChunker(BaseChunker):
    """Chunker placeholder that will later split text by size windows."""

    name = "fixed_size"

    def chunk(self, request: ChunkingRequest) -> list[Chunk]:
        """Create fixed-size chunks from parsed content.

        TODO:
        - define chunk size and overlap semantics
        - map chunks back to source pages and blocks
        - retain parser metadata for downstream comparisons
        """

        raise NotImplementedError("TODO: implement the fixed-size chunker.")

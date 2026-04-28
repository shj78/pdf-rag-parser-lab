"""Common data contracts shared across parser, chunking, retrieval, and eval.

These schema definitions are intentionally lightweight. They exist to make the
experiment boundaries explicit before any concrete implementation begins.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class BoundingBox:
    """Optional page-level coordinates for extracted blocks."""

    x0: float | None = None
    y0: float | None = None
    x1: float | None = None
    y1: float | None = None


@dataclass(slots=True)
class TextBlock:
    """Container for parser-produced text segments."""

    block_id: str
    page_number: int
    text: str
    bbox: BoundingBox | None = None
    block_type: str = "text"
    section_title: str | None = None
    heading_path: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TableBlock:
    """Container for parser-produced table segments.

    Table metadata fields are included explicitly so parser outputs can be
    compared for table fidelity and structure preservation later.
    """

    table_id: str
    page_number: int
    parser_name: str
    row_count: int | None = None
    col_count: int | None = None
    markdown: str | None = None
    raw_cells: list[list[str]] = field(default_factory=list)
    caption: str | None = None
    bbox: BoundingBox | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ParsedPage:
    """A single parsed page with separated text and table blocks."""

    page_number: int
    page_text: str = ""
    text_blocks: list[TextBlock] = field(default_factory=list)
    table_blocks: list[TableBlock] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ParsedDocument:
    """Parser output at the document level."""

    document_id: str
    source_path: str
    parser_name: str
    pages: list[ParsedPage] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Chunk:
    """Chunk contract shared between chunking and retrieval stages."""

    chunk_id: str
    document_id: str
    text: str
    page_number: int | None = None
    chunk_type: str = "text"
    section_title: str | None = None
    heading_path: list[str] = field(default_factory=list)
    parser_name: str = ""
    source_block_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RetrievalResult:
    """Retrieval or reranking output tied back to a chunk."""

    query_id: str
    chunk_id: str
    document_id: str
    parser_name: str
    score: float | None = None
    rank: int | None = None
    page_number: int | None = None
    rerank_score: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

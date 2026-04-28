"""Metadata contracts used across parsing, chunking, and retrieval."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class DocumentMetadata:
    """Top-level document metadata."""

    document_id: str
    file_name: str
    parser_name: str
    source_path: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ChunkMetadata:
    """Chunk-level metadata to support later filtering experiments."""

    document_id: str
    file_name: str
    parser_name: str
    page_number: int | None = None
    chunk_type: str = "text"
    section_title: str | None = None
    heading_path: list[str] = field(default_factory=list)
    has_table: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MetadataFilterSpec:
    """Planned filter contract for later metadata filtering experiments."""

    parser_name: str | None = None
    page_number: int | None = None
    chunk_type: str | None = None
    section_title: str | None = None
    heading_path: list[str] = field(default_factory=list)
    has_table: bool | None = None

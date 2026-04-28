"""Parser-specific contracts layered on top of common document schemas."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ParserConfig:
    """Configuration envelope for parser adapters."""

    parser_name: str
    parse_tables: bool = True
    preserve_layout: bool = True
    emit_page_images: bool = False
    is_baseline: bool = False
    extra_options: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ParseRequest:
    """Input contract for a parser run."""

    document_id: str
    source_path: Path
    config: ParserConfig


@dataclass(slots=True)
class ParserDescriptor:
    """Human-readable parser metadata for UIs and experiments."""

    name: str
    display_name: str
    description: str
    is_baseline: bool = False
    strengths: list[str] = field(default_factory=list)
    known_limitations: list[str] = field(default_factory=list)

"""Artifact serialization helpers for experiment outputs."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from src.schemas import BoundingBox, ParsedDocument, ParsedPage, TableBlock, TextBlock


def ensure_directory(path: Path) -> Path:
    """Create the directory if it does not already exist."""

    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: str | Path, payload: dict[str, Any]) -> Path:
    """Write a JSON artifact with stable formatting."""

    output_path = Path(path)
    ensure_directory(output_path.parent)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def read_json(path: str | Path) -> dict[str, Any]:
    """Read a JSON artifact from disk."""

    return json.loads(Path(path).read_text(encoding="utf-8"))


def parsed_document_to_dict(document: ParsedDocument) -> dict[str, Any]:
    """Convert a parsed document dataclass tree into plain dictionaries."""

    return asdict(document)


def parsed_document_from_dict(payload: dict[str, Any]) -> ParsedDocument:
    """Rebuild a ParsedDocument from a serialized dictionary."""

    pages = [
        ParsedPage(
            page_number=page_payload["page_number"],
            page_text=page_payload.get("page_text", ""),
            text_blocks=[
                TextBlock(
                    block_id=text_payload["block_id"],
                    page_number=text_payload["page_number"],
                    text=text_payload.get("text", ""),
                    bbox=_bbox_from_dict(text_payload.get("bbox")),
                    block_type=text_payload.get("block_type", "text"),
                    section_title=text_payload.get("section_title"),
                    heading_path=text_payload.get("heading_path", []),
                    metadata=text_payload.get("metadata", {}),
                )
                for text_payload in page_payload.get("text_blocks", [])
            ],
            table_blocks=[
                TableBlock(
                    table_id=table_payload["table_id"],
                    page_number=table_payload["page_number"],
                    parser_name=table_payload["parser_name"],
                    row_count=table_payload.get("row_count"),
                    col_count=table_payload.get("col_count"),
                    markdown=table_payload.get("markdown"),
                    raw_cells=table_payload.get("raw_cells", []),
                    caption=table_payload.get("caption"),
                    bbox=_bbox_from_dict(table_payload.get("bbox")),
                    metadata=table_payload.get("metadata", {}),
                )
                for table_payload in page_payload.get("table_blocks", [])
            ],
            metadata=page_payload.get("metadata", {}),
        )
        for page_payload in payload.get("pages", [])
    ]

    return ParsedDocument(
        document_id=payload["document_id"],
        source_path=payload["source_path"],
        parser_name=payload["parser_name"],
        pages=pages,
        metadata=payload.get("metadata", {}),
        warnings=payload.get("warnings", []),
    )


def write_parsed_document(path: str | Path, document: ParsedDocument) -> Path:
    """Persist a ParsedDocument as JSON."""

    return write_json(path, parsed_document_to_dict(document))


def load_parsed_document(path: str | Path) -> ParsedDocument:
    """Load a ParsedDocument artifact from JSON."""

    return parsed_document_from_dict(read_json(path))


def _bbox_from_dict(payload: dict[str, Any] | None) -> BoundingBox | None:
    if payload is None:
        return None

    return BoundingBox(
        x0=payload.get("x0"),
        y0=payload.get("y0"),
        x1=payload.get("x1"),
        y1=payload.get("y1"),
    )

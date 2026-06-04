"""Fixed-size chunker for ParsedDocument artifacts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from src.schemas import Chunk, ParsedDocument, TableBlock

from .base import BaseChunker, ChunkingRequest

DEFAULT_CHUNK_SIZE = 800
DEFAULT_OVERLAP = 120
_MONTH_PATTERN = re.compile(r"(?<!\d)(1[0-2]|[1-9])\s*월")


@dataclass(slots=True)
class _ChunkSource:
    text: str
    page_number: int
    chunk_type: str
    source_block_ids: list[str]
    section_title: str | None
    heading_path: list[str]
    metadata: dict[str, object]


class FixedSizeChunker(BaseChunker):
    """Split parser output into fixed-size character windows."""

    name = "fixed_size"

    def chunk(self, request: ChunkingRequest) -> list[Chunk]:
        """Create fixed-size chunks from parsed text and table blocks."""

        chunk_size = request.config.target_chunk_size or DEFAULT_CHUNK_SIZE
        overlap = request.config.overlap or DEFAULT_OVERLAP
        extra_options = request.config.extra_options
        if chunk_size <= 0:
            raise ValueError("target_chunk_size must be greater than zero")
        if overlap < 0:
            raise ValueError("overlap must be zero or greater")
        if overlap >= chunk_size:
            raise ValueError("overlap must be smaller than target_chunk_size")

        chunks: list[Chunk] = []
        for source in _iter_chunk_sources(
            request.document,
            prepend_page_text_to_tables=_bool_option(
                extra_options,
                "prepend_page_text_to_tables",
            ),
            table_context_strategy=str(
                extra_options.get("table_context_strategy", "page_text")
            ),
        ):
            for window_index, window_text in enumerate(
                _split_text(source.text, chunk_size, overlap),
                start=1,
            ):
                chunks.append(
                    Chunk(
                        chunk_id=(
                            f"{request.document.document_id}:"
                            f"{request.document.parser_name}:"
                            f"p{source.page_number}:"
                            f"{source.chunk_type}:{len(chunks) + 1}"
                        ),
                        document_id=request.document.document_id,
                        text=window_text,
                        page_number=source.page_number,
                        chunk_type=source.chunk_type,
                        section_title=source.section_title,
                        heading_path=list(source.heading_path),
                        parser_name=request.document.parser_name,
                        source_block_ids=list(source.source_block_ids),
                        metadata={
                            **source.metadata,
                            "chunker_name": self.name,
                            "window_index": window_index,
                            "target_chunk_size": chunk_size,
                            "overlap": overlap,
                        },
                    )
                )
        return chunks


def _iter_chunk_sources(
    document: ParsedDocument,
    *,
    prepend_page_text_to_tables: bool = False,
    table_context_strategy: str = "page_text",
) -> list[_ChunkSource]:
    sources: list[_ChunkSource] = []
    for page in document.pages:
        text_blocks = [block for block in page.text_blocks if block.text.strip()]
        table_contexts = _table_contexts(
            text_blocks,
            len(page.table_blocks),
            prepend_page_text_to_tables=prepend_page_text_to_tables,
            table_context_strategy=table_context_strategy,
        )
        if len(text_blocks) == 1:
            block = text_blocks[0]
            sources.append(
                _ChunkSource(
                    text=block.text.strip(),
                    page_number=page.page_number,
                    chunk_type=block.block_type or "text",
                    source_block_ids=[block.block_id],
                    section_title=block.section_title,
                    heading_path=list(block.heading_path),
                    metadata={
                        "source_kind": "text_block",
                        "parser_name": document.parser_name,
                    },
                )
            )
        elif len(text_blocks) > 1:
            sources.append(
                _ChunkSource(
                    text="\n".join(block.text.strip() for block in text_blocks),
                    page_number=page.page_number,
                    chunk_type="page_text",
                    source_block_ids=[block.block_id for block in text_blocks],
                    section_title=None,
                    heading_path=[],
                    metadata={
                        "source_kind": "page_text_from_text_blocks",
                        "parser_name": document.parser_name,
                        "text_block_count": len(text_blocks),
                    },
                )
            )

        for table_index, table in enumerate(page.table_blocks):
            table_text = _table_text(table)
            if not table_text:
                continue
            context_text = table_contexts[table_index] if table_index < len(table_contexts) else None
            context_metadata = _table_context_metadata(context_text, text_blocks)
            if context_text:
                table_text = f"{context_text}\n{table_text}"
            sources.append(
                _ChunkSource(
                    text=table_text,
                    page_number=page.page_number,
                    chunk_type="table",
                    source_block_ids=[table.table_id],
                    section_title=table.caption or context_text,
                    heading_path=[],
                    metadata={
                        "source_kind": "table_block",
                        "parser_name": document.parser_name,
                        "row_count": table.row_count,
                        "col_count": table.col_count,
                        "has_table": True,
                        **context_metadata,
                    },
                )
            )

        if page.page_text.strip() and not page.text_blocks and not page.table_blocks:
            sources.append(
                _ChunkSource(
                    text=page.page_text.strip(),
                    page_number=page.page_number,
                    chunk_type="page_text",
                    source_block_ids=[],
                    section_title=None,
                    heading_path=[],
                    metadata={
                        "source_kind": "page_text",
                        "parser_name": document.parser_name,
                    },
                )
            )
    return sources


def _table_contexts(
    text_blocks: list[Any],
    table_count: int,
    *,
    prepend_page_text_to_tables: bool,
    table_context_strategy: str,
) -> list[str | None]:
    if not prepend_page_text_to_tables or table_count == 0:
        return [None] * table_count

    page_context = "\n".join(block.text.strip() for block in text_blocks if block.text.strip())
    if not page_context:
        return [None] * table_count

    if table_context_strategy == "calendar_month":
        month_contexts = _calendar_month_contexts(text_blocks, table_count)
        if month_contexts:
            return month_contexts

    return [page_context] * table_count


def _calendar_month_contexts(
    text_blocks: list[Any],
    table_count: int,
) -> list[str | None]:
    month_numbers = _month_numbers_from_text_blocks(text_blocks)
    if not month_numbers:
        return []
    if len(month_numbers) == table_count:
        return [_month_label(month_number) for month_number in month_numbers]
    if len(month_numbers) > table_count:
        if table_count == 2:
            return [_month_label(month_numbers[0]), _month_label(month_numbers[-1])]
        return [_month_label(month_number) for month_number in month_numbers[:table_count]]

    if len(month_numbers) >= 2 and table_count > len(month_numbers):
        first_month = month_numbers[0]
        last_month = month_numbers[-1]
        inferred = [_next_month(first_month, offset) for offset in range(table_count)]
        if inferred[-1] == last_month:
            return [_month_label(month_number) for month_number in inferred]
    return []


def _month_numbers_from_text_blocks(text_blocks: list[Any]) -> list[int]:
    month_numbers: list[int] = []
    for block in text_blocks:
        for match in _MONTH_PATTERN.finditer(block.text):
            month_number = int(match.group(1))
            if month_number not in month_numbers:
                month_numbers.append(month_number)
    return month_numbers


def _next_month(first_month: int, offset: int) -> int:
    return ((first_month - 1 + offset) % 12) + 1


def _month_label(month_number: int) -> str:
    return f"{month_number}월"


def _table_context_metadata(
    context_text: str | None,
    text_blocks: list[Any],
) -> dict[str, object]:
    if not context_text:
        return {}
    return {
        "prepended_page_text_to_table": True,
        "context_title": context_text,
        "context_source_kind": "page_text_blocks",
        "context_source_block_ids": [block.block_id for block in text_blocks],
    }


def _table_text(table: TableBlock) -> str:
    markdown = (table.markdown or "").strip()
    if markdown:
        return markdown

    rows: list[str] = []
    for row in table.raw_cells:
        cells = [str(cell).strip() for cell in row if str(cell).strip()]
        if cells:
            rows.append(" | ".join(cells))
    return "\n".join(rows)


def _bool_option(options: dict[str, Any], key: str) -> bool:
    value = options.get(key, False)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _split_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    stripped = " ".join(text.split())
    if not stripped:
        return []

    windows: list[str] = []
    step = chunk_size - overlap
    start = 0
    while start < len(stripped):
        window = stripped[start : start + chunk_size].strip()
        if window:
            windows.append(window)
        if start + chunk_size >= len(stripped):
            break
        start += step
    return windows

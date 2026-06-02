"""Fixed-size chunker for ParsedDocument artifacts."""

from __future__ import annotations

from dataclasses import dataclass

from src.schemas import Chunk, ParsedDocument, TableBlock

from .base import BaseChunker, ChunkingRequest

DEFAULT_CHUNK_SIZE = 800
DEFAULT_OVERLAP = 120


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
        if chunk_size <= 0:
            raise ValueError("target_chunk_size must be greater than zero")
        if overlap < 0:
            raise ValueError("overlap must be zero or greater")
        if overlap >= chunk_size:
            raise ValueError("overlap must be smaller than target_chunk_size")

        chunks: list[Chunk] = []
        for source in _iter_chunk_sources(request.document):
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


def _iter_chunk_sources(document: ParsedDocument) -> list[_ChunkSource]:
    sources: list[_ChunkSource] = []
    for page in document.pages:
        text_blocks = [block for block in page.text_blocks if block.text.strip()]
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

        for table in page.table_blocks:
            table_text = _table_text(table)
            if not table_text:
                continue
            sources.append(
                _ChunkSource(
                    text=table_text,
                    page_number=page.page_number,
                    chunk_type="table",
                    source_block_ids=[table.table_id],
                    section_title=table.caption,
                    heading_path=[],
                    metadata={
                        "source_kind": "table_block",
                        "parser_name": document.parser_name,
                        "row_count": table.row_count,
                        "col_count": table.col_count,
                        "has_table": True,
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

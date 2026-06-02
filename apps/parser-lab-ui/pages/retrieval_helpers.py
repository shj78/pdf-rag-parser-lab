"""Helpers shared by retrieval-oriented Streamlit pages."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.artifacts import load_parsed_document
from src.chunkers.base import ChunkerConfig, ChunkingRequest
from src.chunkers.fixed_size_chunker import FixedSizeChunker
from src.retrieval.index import IndexConfig, LexicalInMemoryIndex, SearchRequest
from src.schemas import Chunk, RetrievalResult

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RUNS_DIR = PROJECT_ROOT / "artifacts" / "parser-lab-ui-runs"


def list_parser_runs() -> list[Path]:
    if not DEFAULT_RUNS_DIR.exists():
        return []
    return sorted(
        [path for path in DEFAULT_RUNS_DIR.iterdir() if path.is_dir()],
        reverse=True,
    )


def load_chunks_from_run(
    run_dir: Path,
    *,
    target_chunk_size: int,
    overlap: int,
) -> list[Chunk]:
    chunker = FixedSizeChunker()
    chunks: list[Chunk] = []
    for artifact_path in sorted((run_dir / "parsed_documents").glob("*/*.json")):
        document = load_parsed_document(artifact_path)
        chunks.extend(
            chunker.chunk(
                ChunkingRequest(
                    document=document,
                    config=ChunkerConfig(
                        chunker_name=chunker.name,
                        target_chunk_size=target_chunk_size,
                        overlap=overlap,
                        parser_name=document.parser_name,
                    ),
                )
            )
        )
    return chunks


def summarize_run_content(run_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for artifact_path in sorted((run_dir / "parsed_documents").glob("*/*.json")):
        document = load_parsed_document(artifact_path)
        text_block_count = 0
        table_block_count = 0
        page_text_chars = 0
        text_block_chars = 0
        table_chars = 0

        for page in document.pages:
            page_text_chars += len(page.page_text.strip())
            text_block_count += len(page.text_blocks)
            table_block_count += len(page.table_blocks)
            text_block_chars += sum(len(block.text.strip()) for block in page.text_blocks)
            table_chars += sum(_table_text_length(table.raw_cells, table.markdown) for table in page.table_blocks)

        rows.append(
            {
                "파서": document.parser_name,
                "문서": document.document_id,
                "페이지": len(document.pages),
                "텍스트 블록": text_block_count,
                "표 블록": table_block_count,
                "페이지 텍스트 문자": page_text_chars,
                "블록 텍스트 문자": text_block_chars,
                "표 문자": table_chars,
                "경고": len(document.warnings),
                "artifact": str(artifact_path.resolve().relative_to(PROJECT_ROOT)),
            }
        )
    return rows


def search_chunks(
    chunks: list[Chunk],
    *,
    query: str,
    top_k: int,
    filters: dict[str, Any] | None = None,
) -> list[RetrievalResult]:
    index = LexicalInMemoryIndex(IndexConfig(backend_name="lexical_in_memory"))
    index.build(chunks)
    return index.search(
        SearchRequest(
            query_id="ui-query",
            query_text=query,
            top_k=top_k,
            filters=filters or {},
        )
    )


def chunks_to_rows(chunks: list[Chunk]) -> list[dict[str, Any]]:
    return [
        {
            "파서": chunk.parser_name,
            "문서": chunk.document_id,
            "페이지": chunk.page_number,
            "유형": chunk.chunk_type,
            "문자 수": len(chunk.text),
            "미리보기": chunk.text[:160],
        }
        for chunk in chunks
    ]


def _table_text_length(raw_cells: list[list[str]], markdown: str | None) -> int:
    if markdown and markdown.strip():
        return len(markdown.strip())
    return sum(
        len(str(cell).strip())
        for row in raw_cells
        for cell in row
        if str(cell).strip()
    )


def results_to_rows(results: list[RetrievalResult]) -> list[dict[str, Any]]:
    return [
        {
            "순위": result.rank,
            "점수": result.score,
            "파서": result.parser_name,
            "문서": result.document_id,
            "페이지": result.page_number,
            "유형": result.metadata.get("chunk_type"),
            "미리보기": result.metadata.get("text_preview"),
            "chunk_id": result.chunk_id,
        }
        for result in results
    ]


def results_to_answer_draft(results: list[RetrievalResult], *, max_sources: int = 3) -> str:
    lines = [
        "현재 QA는 LLM 생성 답변이 아니라 상위 검색 근거를 묶은 임시 답변입니다.",
        "",
    ]
    for result in results[:max_sources]:
        preview = str(result.metadata.get("text_preview") or "").strip()
        if not preview:
            continue
        lines.append(
            f"- {result.parser_name} / {result.page_number}페이지 / "
            f"점수 {result.score}: {preview}"
        )
    return "\n".join(lines).strip()

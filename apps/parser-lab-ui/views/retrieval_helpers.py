"""Helpers shared by retrieval-oriented Streamlit pages."""

from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

from src.artifacts import load_parsed_document
from src.chunkers.base import ChunkerConfig, ChunkingRequest
from src.chunkers.fixed_size_chunker import FixedSizeChunker
from src.retrieval.embeddings import EmbeddingConfig, create_embedding_provider
from src.retrieval.index import (
    EmbeddingInMemoryIndex,
    IndexConfig,
    LexicalInMemoryIndex,
)
from src.retrieval.retriever import RetrievalPipelineConfig, Retriever
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
    index_backend: str = "lexical_in_memory",
    embedding_provider: str | None = None,
    embedding_model: str | None = None,
    embedding_options: dict[str, Any] | None = None,
) -> list[RetrievalResult]:
    index = _build_index(
        index_backend=index_backend,
        embedding_provider=embedding_provider,
        embedding_model=embedding_model,
        embedding_options=embedding_options or {},
    )
    index.build(chunks)
    retriever = Retriever(
        vector_index=index,
        config=RetrievalPipelineConfig(
            top_k_before_rerank=top_k,
            top_k_after_rerank=top_k,
            enable_reranker=False,
            metadata_filters=filters or {},
        )
    )
    results = retriever.retrieve(query_id="ui-query", query_text=query)
    if results:
        return results
    if index_backend != "lexical_in_memory":
        return results
    return _fallback_search_chunks(chunks, query=query, top_k=top_k, filters=filters)


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


def _build_index(
    *,
    index_backend: str,
    embedding_provider: str | None,
    embedding_model: str | None,
    embedding_options: dict[str, Any],
) -> LexicalInMemoryIndex | EmbeddingInMemoryIndex:
    if index_backend == "lexical_in_memory":
        return LexicalInMemoryIndex(IndexConfig(backend_name=index_backend))
    if index_backend == "embedding_in_memory":
        provider_name = embedding_provider or "hashing"
        model_name = embedding_model or "hashing-token-v1"
        provider = create_embedding_provider(
            EmbeddingConfig(
                provider_name=provider_name,
                model_name=model_name,
                extra_options=embedding_options,
            )
        )
        return EmbeddingInMemoryIndex(
            embedding_provider=provider,
            config=IndexConfig(backend_name=index_backend),
        )
    raise ValueError(f"지원하지 않는 검색 backend입니다: {index_backend}")


def _fallback_search_chunks(
    chunks: list[Chunk],
    *,
    query: str,
    top_k: int,
    filters: dict[str, Any] | None,
) -> list[RetrievalResult]:
    filtered_chunks = [
        chunk for chunk in chunks if _matches_ui_filters(chunk, filters or {})
    ]
    if not filtered_chunks:
        return []

    query_vector = Counter(_char_ngrams(query))
    scored: list[tuple[float, Chunk]] = []
    for chunk in filtered_chunks:
        score = _cosine(query_vector, Counter(_char_ngrams(chunk.text)))
        scored.append((score, chunk))

    scored.sort(key=lambda item: item[0], reverse=True)
    if scored and scored[0][0] <= 0:
        scored = [
            (1.0 / (index + 1), chunk)
            for index, chunk in enumerate(filtered_chunks[:top_k])
        ]

    results: list[RetrievalResult] = []
    for rank, (score, chunk) in enumerate(scored[:top_k], start=1):
        results.append(
            RetrievalResult(
                query_id="ui-query",
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                parser_name=chunk.parser_name,
                score=round(score, 6),
                rank=rank,
                page_number=chunk.page_number,
                metadata={
                    **chunk.metadata,
                    "chunk_type": chunk.chunk_type,
                    "section_title": chunk.section_title,
                    "heading_path": chunk.heading_path,
                    "text_preview": chunk.text[:500],
                    "source_block_ids": chunk.source_block_ids,
                    "retrieval_fallback": True,
                },
            )
        )
    return results


def _char_ngrams(text: str, n: int = 2) -> list[str]:
    compact = "".join(re.findall(r"[0-9A-Za-z가-힣]+", text.lower()))
    if not compact:
        return []
    if len(compact) <= n:
        return [compact]
    return [compact[index : index + n] for index in range(len(compact) - n + 1)]


def _cosine(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    numerator = sum(left[token] * right.get(token, 0) for token in left)
    if numerator == 0:
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def _matches_ui_filters(chunk: Chunk, filters: dict[str, Any]) -> bool:
    for key, value in filters.items():
        if value in (None, "", [], ()):
            continue
        if key == "parser_name" and chunk.parser_name != value:
            return False
        if key == "chunk_type" and chunk.chunk_type != value:
            return False
        if key == "page_number" and chunk.page_number != int(value):
            return False
        if key == "has_table":
            has_table = chunk.chunk_type == "table" or bool(chunk.metadata.get("has_table"))
            if bool(value) != has_table:
                return False
        if key not in {"parser_name", "chunk_type", "page_number", "has_table"}:
            if chunk.metadata.get(key) != value:
                return False
    return True

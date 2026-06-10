"""Helpers shared by retrieval-oriented Streamlit pages."""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

from src.artifacts import load_parsed_document, read_json
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
DEFAULT_RETRIEVAL_EVAL_RUNS_DIR = PROJECT_ROOT / "artifacts" / "retrieval-eval-runs"


def list_parser_runs() -> list[Path]:
    if not DEFAULT_RUNS_DIR.exists():
        return []
    return sorted(
        [path for path in DEFAULT_RUNS_DIR.iterdir() if path.is_dir()],
        reverse=True,
    )


def list_retrieval_eval_runs() -> list[Path]:
    if not DEFAULT_RETRIEVAL_EVAL_RUNS_DIR.exists():
        return []
    return sorted(
        [
            path
            for path in DEFAULT_RETRIEVAL_EVAL_RUNS_DIR.iterdir()
            if path.is_dir() and (path / "evaluation_result.json").exists()
        ],
        reverse=True,
    )


def load_retrieval_eval_artifacts(run_dir: Path) -> dict[str, Any]:
    manifest = _read_json_if_exists(run_dir / "run_manifest.json")
    return {
        "summary": _read_json_if_exists(run_dir / "run_summary.json"),
        "evaluation": read_json(run_dir / "evaluation_result.json"),
        "rankings": _read_json_if_exists(run_dir / "rankings.json"),
        "chunks": _read_json_if_exists(run_dir / "chunks.json"),
        "manifest": manifest,
        "labels": _load_labels_from_manifest(manifest, run_dir),
        "queries": _load_queries_from_manifest(manifest, run_dir),
    }


def retrieval_eval_summary(artifacts: dict[str, Any]) -> dict[str, Any]:
    """Return display summary values derived from the actual eval artifacts."""

    summary = artifacts.get("summary") or {}
    rankings = artifacts.get("rankings") or {}
    evaluation = artifacts.get("evaluation") or {}
    ranking_queries = rankings.get("queries") or []
    query_results = evaluation.get("query_results") or {}
    chunks_payload = artifacts.get("chunks") or {}

    query_count = len(ranking_queries) or len(query_results) or summary.get("query_count", 0)
    label_count = len(artifacts.get("labels") or []) or summary.get("label_count", 0)
    chunk_count = _chunk_count(chunks_payload) or summary.get("chunk_count", 0)
    top_k = _ranking_top_k(ranking_queries) or summary.get("top_k", "-")

    return {
        **summary,
        "query_count": query_count,
        "label_count": label_count,
        "chunk_count": chunk_count,
        "top_k": top_k,
    }


def aggregate_score_rows(artifacts: dict[str, Any]) -> list[dict[str, Any]]:
    summary = artifacts.get("summary") or {}
    evaluation = artifacts.get("evaluation") or {}
    scores = summary.get("scores") or evaluation.get("scores") or []
    return [
        {
            "지표": _metric_label(score),
            "점수": round(float(score.get("value", 0.0)), 4),
            "메모": score.get("notes") or "",
        }
        for score in sorted(scores, key=_score_sort_key)
    ]


def retrieval_eval_comparison_rows(
    run_artifacts: list[tuple[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for run_name, artifacts in run_artifacts:
        summary = retrieval_eval_summary(artifacts)
        score_by_metric = {
            str(row["지표"]): float(row["점수"])
            for row in aggregate_score_rows(artifacts)
        }
        row: dict[str, Any] = {
            "run": run_name,
            "전략": _strategy_label(summary),
            "질문": summary.get("query_count", 0),
            "라벨": summary.get("label_count", 0),
            "chunk": summary.get("chunk_count", 0),
            "top-k": summary.get("top_k", "-"),
        }
        for metric in sorted(score_by_metric, key=_metric_name_sort_key):
            row[metric.upper()] = round(score_by_metric[metric], 3)
        rows.append(row)
    return rows


def retrieval_eval_delta_rows(
    baseline_artifacts: dict[str, Any],
    candidate_artifacts: dict[str, Any],
) -> list[dict[str, Any]]:
    baseline_scores = {
        str(row["지표"]): float(row["점수"])
        for row in aggregate_score_rows(baseline_artifacts)
    }
    candidate_scores = {
        str(row["지표"]): float(row["점수"])
        for row in aggregate_score_rows(candidate_artifacts)
    }
    rows: list[dict[str, Any]] = []
    for metric in sorted(set(baseline_scores) & set(candidate_scores), key=_metric_name_sort_key):
        before = baseline_scores[metric]
        after = candidate_scores[metric]
        rows.append(
            {
                "지표": metric.upper(),
                "baseline": round(before, 3),
                "candidate": round(after, 3),
                "개선폭": round(after - before, 3),
            }
        )
    return rows


def query_score_rows(artifacts: dict[str, Any]) -> list[dict[str, Any]]:
    evaluation = artifacts.get("evaluation") or {}
    rankings = artifacts.get("rankings") or {}
    query_text_by_id = {
        str(query["query_id"]): str(query.get("query_text", ""))
        for query in rankings.get("queries", [])
    }
    query_metadata_by_id = _query_metadata_by_id(artifacts)
    query_order = list(query_text_by_id)
    query_results = evaluation.get("query_results", {})
    ordered_query_ids = [
        *[query_id for query_id in query_order if query_id in query_results],
        *[query_id for query_id in query_results if query_id not in query_text_by_id],
    ]

    rows: list[dict[str, Any]] = []
    for query_id in ordered_query_ids:
        row: dict[str, Any] = {
            "query_id": query_id,
            "질문": query_text_by_id.get(query_id, ""),
        }
        metadata = query_metadata_by_id.get(query_id, {})
        if metadata:
            row["유형"] = _question_type_label(str(metadata.get("question_type", "")))
            row["난이도"] = str(metadata.get("difficulty", ""))
        for score in query_results.get(query_id, []):
            row[_metric_label(score)] = round(float(score.get("value", 0.0)), 4)
        rows.append(row)
    return rows


def query_diagnostic_rows(artifacts: dict[str, Any]) -> list[dict[str, Any]]:
    """Build portfolio-friendly per-query diagnosis rows."""

    rows: list[dict[str, Any]] = []
    query_metadata_by_id = _query_metadata_by_id(artifacts)
    for score_row in query_score_rows(artifacts):
        query_id = str(score_row["query_id"])
        metadata = query_metadata_by_id.get(query_id, {})
        first_relevant_rank = _first_labeled_rank(artifacts, query_id, min_grade=1)
        first_direct_rank = _first_labeled_rank(artifacts, query_id, min_grade=2)
        ndcg_at_1 = float(score_row.get("ndcg@1", 0.0))
        ndcg_at_5 = float(score_row.get("ndcg@5", 0.0))
        ndcg_at_10 = float(score_row.get("ndcg@10", score_row.get("ndcg@5", 0.0)))
        rows.append(
            {
                "질문 ID": query_id,
                "유형": _question_type_label(str(metadata.get("question_type", ""))),
                "난이도": str(metadata.get("difficulty", "")),
                "NDCG@1": round(ndcg_at_1, 3),
                "NDCG@5": round(ndcg_at_5, 3),
                "NDCG@10": round(ndcg_at_10, 3),
                "첫 관련 근거": _rank_label(first_relevant_rank),
                "첫 직접 근거": _rank_label(first_direct_rank),
                "판정": _diagnosis_label(first_direct_rank, ndcg_at_1, ndcg_at_10),
                "질문": score_row.get("질문", ""),
            }
        )
    return rows


def ranking_rows(
    artifacts: dict[str, Any],
    *,
    query_id: str,
    max_results: int = 10,
) -> list[dict[str, Any]]:
    query_payload = _ranking_query_payload(artifacts, query_id)
    if not query_payload:
        return []

    labels_by_chunk = _labels_by_chunk_id(artifacts, query_id)
    rows: list[dict[str, Any]] = []
    for result in query_payload.get("results", [])[:max_results]:
        metadata = result.get("metadata", {})
        label = labels_by_chunk.get(str(result.get("chunk_id")))
        rows.append(
            {
                "순위": result.get("rank"),
                "라벨": label.get("grade") if label else None,
                "점수": round(float(result.get("score", 0.0)), 6),
                "리랭크 점수": _optional_round(result.get("rerank_score")),
                "파서": result.get("parser_name"),
                "페이지": result.get("page_number"),
                "유형": metadata.get("chunk_type"),
                "섹션": metadata.get("section_title") or metadata.get("context_title"),
                "미리보기": metadata.get("text_preview"),
                "chunk_id": result.get("chunk_id"),
                "라벨 근거": label.get("rationale") if label else "",
            }
        )
    return rows


def query_text_for_run(artifacts: dict[str, Any], query_id: str) -> str:
    query_payload = _ranking_query_payload(artifacts, query_id)
    if not query_payload:
        return ""
    return str(query_payload.get("query_text", ""))


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


def _read_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return read_json(path)


def _load_labels_from_manifest(
    manifest: dict[str, Any],
    run_dir: Path,
) -> list[dict[str, Any]]:
    raw_path = manifest.get("relevance_labels_path")
    if not raw_path:
        return []
    labels_path = Path(str(raw_path)).expanduser()
    candidate_paths = [
        labels_path,
        PROJECT_ROOT / labels_path,
        run_dir / labels_path,
    ]
    for candidate_path in candidate_paths:
        if candidate_path.exists():
            return _read_jsonl(candidate_path)
    return []


def _load_queries_from_manifest(
    manifest: dict[str, Any],
    run_dir: Path,
) -> list[dict[str, Any]]:
    raw_path = manifest.get("query_set_path")
    if not raw_path:
        return []
    query_path = Path(str(raw_path)).expanduser()
    candidate_paths = [
        query_path,
        PROJECT_ROOT / query_path,
        run_dir / query_path,
    ]
    for candidate_path in candidate_paths:
        if candidate_path.exists():
            return _read_jsonl(candidate_path)
    return []


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped:
            rows.append(json.loads(stripped))
    return rows


def _chunk_count(chunks_payload: Any) -> int:
    if isinstance(chunks_payload, list):
        return len(chunks_payload)
    if isinstance(chunks_payload, dict):
        chunks = chunks_payload.get("chunks")
        if isinstance(chunks, list):
            return len(chunks)
    return 0


def _ranking_top_k(ranking_queries: list[dict[str, Any]]) -> int:
    result_counts = [
        len(query.get("results") or [])
        for query in ranking_queries
        if isinstance(query.get("results"), list)
    ]
    return max(result_counts, default=0)


def _metric_label(score: dict[str, Any]) -> str:
    metric_name = str(score.get("metric_name", "metric"))
    k = score.get("k")
    if k is None:
        return metric_name
    return f"{metric_name}@{k}"


def _score_sort_key(score: dict[str, Any]) -> tuple[str, int]:
    metric_name = str(score.get("metric_name", "metric"))
    k = score.get("k")
    return (metric_name, int(k) if k is not None else 0)


def _metric_name_sort_key(metric: str) -> tuple[str, int]:
    name, _, raw_k = metric.partition("@")
    return (name, int(raw_k) if raw_k.isdigit() else 0)


def _strategy_label(summary: dict[str, Any]) -> str:
    backend = str(summary.get("index_backend") or "-")
    if summary.get("reranker_enabled"):
        return f"{backend} + reranker"
    return backend


def _query_metadata_by_id(artifacts: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(query.get("query_id")): dict(query.get("metadata") or {})
        for query in artifacts.get("queries", [])
    }


def _question_type_label(question_type: str) -> str:
    labels = {
        "single_hop_fact": "단순 사실",
        "multi_hop_reasoning": "복합 추론",
        "table_extraction": "표 추출",
        "condition_based": "조건/예외",
    }
    return labels.get(question_type, question_type or "-")


def _ranking_query_payload(
    artifacts: dict[str, Any],
    query_id: str,
) -> dict[str, Any] | None:
    rankings = artifacts.get("rankings") or {}
    for query_payload in rankings.get("queries", []):
        if str(query_payload.get("query_id")) == query_id:
            return query_payload
    return None


def _labels_by_chunk_id(
    artifacts: dict[str, Any],
    query_id: str,
) -> dict[str, dict[str, Any]]:
    return {
        str(label["chunk_id"]): label
        for label in artifacts.get("labels", [])
        if str(label.get("query_id")) == query_id
    }


def _first_labeled_rank(
    artifacts: dict[str, Any],
    query_id: str,
    *,
    min_grade: int,
) -> int | None:
    query_payload = _ranking_query_payload(artifacts, query_id)
    if not query_payload:
        return None
    labels_by_chunk = _labels_by_chunk_id(artifacts, query_id)
    for result in query_payload.get("results", []):
        label = labels_by_chunk.get(str(result.get("chunk_id")))
        if label and int(label.get("grade", 0)) >= min_grade:
            return int(result.get("rank", 0))
    return None


def _rank_label(rank: int | None) -> str:
    if rank is None:
        return "top-k 밖"
    return f"{rank}위"


def _diagnosis_label(
    first_direct_rank: int | None,
    ndcg_at_1: float,
    ndcg_at_10: float,
) -> str:
    if first_direct_rank == 1 and ndcg_at_1 >= 0.999:
        return "성공"
    if first_direct_rank is not None and first_direct_rank <= 3:
        return "상위권"
    if first_direct_rank is not None and first_direct_rank <= 10:
        return "후순위"
    if ndcg_at_10 > 0:
        return "부분 검색"
    return "실패"


def _optional_round(value: Any) -> float | None:
    if value is None:
        return None
    return round(float(value), 6)


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

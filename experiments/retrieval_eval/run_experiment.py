"""Runnable retrieval evaluation experiment."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.artifacts import ensure_directory, load_parsed_document, write_json
from src.chunkers.base import ChunkerConfig, ChunkingRequest
from src.chunkers.fixed_size_chunker import FixedSizeChunker
from src.config_loader import load_yaml_config, resolve_path
from src.evaluation.evaluator import EvaluatorConfig, RetrievalEvaluator
from src.evaluation.schemas import (
    EvaluationQuery,
    QueryEvaluationInput,
    RelevanceLabel,
)
from src.retrieval.embeddings import EmbeddingConfig, create_embedding_provider
from src.retrieval.existing_reranker_bridge import (
    ExistingRerankerBridge,
    ExistingRerankerBridgeConfig,
)
from src.retrieval.index import (
    EmbeddingInMemoryIndex,
    IndexConfig,
    LexicalInMemoryIndex,
    VectorIndex,
)
from src.retrieval.reranker_adapter import BaseRerankerAdapter
from src.retrieval.retriever import RetrievalPipelineConfig, Retriever
from src.schemas import Chunk


@dataclass(slots=True)
class RetrievalEvalConfig:
    """Materialized retrieval evaluation configuration."""

    config_path: Path
    run_name: str
    parsed_documents_dir: Path
    query_set_path: Path
    relevance_labels_path: Path | None
    output_dir: Path
    chunker_name: str = "fixed_size"
    target_chunk_size: int = 800
    overlap: int = 120
    index_backend: str = "lexical_in_memory"
    embedding_provider: str = "hashing"
    embedding_model: str = "hashing-token-v1"
    embedding_options: dict[str, Any] = field(default_factory=dict)
    top_k: int = 10
    filters: dict[str, Any] = field(default_factory=dict)
    reranker_enabled: bool = False
    reranker_mode: str = "python_module"
    reranker_entrypoint: str | None = None
    reranker_top_k: int | None = None
    reranker_options: dict[str, Any] = field(default_factory=dict)
    metric_names: list[str] = field(default_factory=lambda: ["ndcg"])
    k_values: list[int] = field(default_factory=lambda: [5, 10])
    save_chunks: bool = True
    save_rankings: bool = True


def build_parser() -> argparse.ArgumentParser:
    """Build the retrieval evaluation CLI."""

    parser = argparse.ArgumentParser(description="Retrieval evaluation runner.")
    parser.add_argument("--config", required=True, help="Path to experiment config.")
    parser.add_argument("--query-set", help="Optional override for query set path.")
    parser.add_argument("--labels", help="Optional override for relevance labels path.")
    parser.add_argument(
        "--parsed-documents",
        help="Optional override for parsed document artifact directory.",
    )
    parser.add_argument("--output-dir", help="Optional override for run output dir.")
    return parser


def load_experiment_config(
    config_path: str | Path,
    query_set_override: str | None = None,
    labels_override: str | None = None,
    parsed_documents_override: str | None = None,
    output_dir_override: str | None = None,
) -> RetrievalEvalConfig:
    """Load and normalize a retrieval evaluation config file."""

    raw_config, config_dir = load_yaml_config(config_path)
    experiment = raw_config.get("experiment", {})
    inputs = raw_config.get("inputs", {})
    chunker = raw_config.get("chunker", {})
    chunker_options = chunker.get("options", {})
    retrieval = raw_config.get("retrieval", {})
    reranker = raw_config.get("reranker", {})
    evaluation = raw_config.get("evaluation", {})
    output = raw_config.get("output", {})

    parsed_documents_dir = _resolve_required_path(
        parsed_documents_override or inputs.get("parsed_documents_dir"),
        config_dir,
        "inputs.parsed_documents_dir",
    )
    query_set_path = _resolve_required_path(
        query_set_override or inputs.get("query_set_path"),
        config_dir,
        "inputs.query_set_path",
    )
    relevance_labels_path = _resolve_optional_path(
        labels_override or inputs.get("relevance_labels_path"),
        config_dir,
    )
    output_dir = (
        Path(output_dir_override).expanduser().resolve()
        if output_dir_override
        else resolve_path(output.get("run_dir", "./runs/retrieval-eval"), config_dir)
    )

    return RetrievalEvalConfig(
        config_path=Path(config_path).expanduser().resolve(),
        run_name=experiment.get("run_name", "retrieval-eval"),
        parsed_documents_dir=parsed_documents_dir,
        query_set_path=query_set_path,
        relevance_labels_path=relevance_labels_path,
        output_dir=output_dir,
        chunker_name=chunker.get("name", "fixed_size"),
        target_chunk_size=int(chunker_options.get("target_chunk_size", 800)),
        overlap=int(chunker_options.get("overlap", 120)),
        index_backend=retrieval.get("index_backend", "lexical_in_memory"),
        embedding_provider=retrieval.get("embedding_provider", "hashing"),
        embedding_model=retrieval.get("embedding_model", "hashing-token-v1"),
        embedding_options=dict(retrieval.get("embedding_options", {})),
        top_k=int(retrieval.get("top_k", 10)),
        filters=dict(retrieval.get("filters", {})),
        reranker_enabled=bool(reranker.get("enabled", False)),
        reranker_mode=reranker.get("mode", "python_module"),
        reranker_entrypoint=reranker.get("entrypoint"),
        reranker_top_k=(
            int(reranker["top_k"])
            if reranker.get("top_k") is not None
            else None
        ),
        reranker_options=dict(reranker.get("options", {})),
        metric_names=_list_value(evaluation.get("metric_names") or evaluation.get("metric"), ["ndcg"]),
        k_values=[int(value) for value in evaluation.get("k_values", [5, 10])],
        save_chunks=bool(output.get("save_chunks", True)),
        save_rankings=bool(output.get("save_rankings", True)),
    )


def run_retrieval_eval(config: RetrievalEvalConfig) -> dict[str, Any]:
    """Execute retrieval evaluation from parsed document artifacts."""

    if config.chunker_name != "fixed_size":
        raise ValueError(f"Unsupported chunker: {config.chunker_name}")
    started_at = datetime.now(timezone.utc).isoformat()
    run_dir = ensure_directory(config.output_dir)
    chunks = _load_chunks(config)
    queries = _load_queries(config.query_set_path)
    relevance_labels = _load_relevance_labels(config.relevance_labels_path)

    index = _build_index(config)
    index.build(chunks)
    reranker = _build_reranker(config)
    retriever = Retriever(
        vector_index=index,
        reranker=reranker,
        config=RetrievalPipelineConfig(
            top_k_before_rerank=config.top_k,
            top_k_after_rerank=config.reranker_top_k or config.top_k,
            enable_reranker=config.reranker_enabled,
            metadata_filters=config.filters,
        ),
    )
    evaluator = RetrievalEvaluator(
        EvaluatorConfig(metric_names=config.metric_names, k_values=config.k_values)
    )

    rankings: list[dict[str, Any]] = []
    evaluation_inputs: list[QueryEvaluationInput] = []
    for query in queries:
        results = retriever.retrieve(query.query_id, query.query_text)
        rankings.append(
            {
                "query_id": query.query_id,
                "query_text": query.query_text,
                "results": [asdict(result) for result in results],
            }
        )
        evaluation_inputs.append(
            QueryEvaluationInput(
                query=query,
                retrieved_results=results,
                relevance_labels=relevance_labels,
                parser_name=_single_value({chunk.parser_name for chunk in chunks}, "mixed"),
                chunker_name=config.chunker_name,
            )
        )

    evaluation_result = evaluator.evaluate_run(
        run_id=run_dir.name,
        parser_name=_single_value({chunk.parser_name for chunk in chunks}, "mixed"),
        chunker_name=config.chunker_name,
        queries=evaluation_inputs,
    )
    completed_at = datetime.now(timezone.utc).isoformat()

    if config.save_chunks:
        write_json(run_dir / "chunks.json", {"chunks": [asdict(chunk) for chunk in chunks]})
    if config.save_rankings:
        write_json(run_dir / "rankings.json", {"queries": rankings})
    write_json(run_dir / "evaluation_result.json", asdict(evaluation_result))

    summary = {
        "run_name": config.run_name,
        "run_dir": str(run_dir),
        "parsed_documents_dir": str(config.parsed_documents_dir),
        "query_count": len(queries),
        "label_count": len(relevance_labels),
        "chunk_count": len(chunks),
        "index_backend": config.index_backend,
        "embedding_provider": (
            config.embedding_provider
            if config.index_backend == "embedding_in_memory"
            else None
        ),
        "embedding_model": (
            config.embedding_model if config.index_backend == "embedding_in_memory" else None
        ),
        "chunker_name": config.chunker_name,
        "top_k": config.top_k,
        "reranker_enabled": config.reranker_enabled,
        "reranker_mode": config.reranker_mode if config.reranker_enabled else None,
        "reranker_entrypoint": (
            config.reranker_entrypoint if config.reranker_enabled else None
        ),
        "reranker_top_k": config.reranker_top_k if config.reranker_enabled else None,
        "scores": [asdict(score) for score in evaluation_result.scores],
        "started_at": started_at,
        "completed_at": completed_at,
    }
    write_json(run_dir / "run_summary.json", summary)
    write_json(
        run_dir / "run_manifest.json",
        {
            **summary,
            "config_path": str(config.config_path),
            "query_set_path": str(config.query_set_path),
            "relevance_labels_path": (
                str(config.relevance_labels_path)
                if config.relevance_labels_path is not None
                else None
            ),
            "filters": config.filters,
            "metric_names": config.metric_names,
            "k_values": config.k_values,
        },
    )
    return summary


def run_retrieval_eval_from_file(
    config_path: str | Path,
    query_set_override: str | None = None,
    labels_override: str | None = None,
    parsed_documents_override: str | None = None,
    output_dir_override: str | None = None,
) -> dict[str, Any]:
    """Load config and run retrieval evaluation in one step."""

    config = load_experiment_config(
        config_path=config_path,
        query_set_override=query_set_override,
        labels_override=labels_override,
        parsed_documents_override=parsed_documents_override,
        output_dir_override=output_dir_override,
    )
    return run_retrieval_eval(config)


def _load_chunks(config: RetrievalEvalConfig) -> list[Chunk]:
    document_paths = _parsed_document_paths(config.parsed_documents_dir)
    if not document_paths:
        raise FileNotFoundError(
            f"No parsed document artifacts found in {config.parsed_documents_dir}"
        )

    chunker = FixedSizeChunker()
    chunks: list[Chunk] = []
    for artifact_path in document_paths:
        document = load_parsed_document(artifact_path)
        chunks.extend(
            chunker.chunk(
                ChunkingRequest(
                    document=document,
                    config=ChunkerConfig(
                        chunker_name=chunker.name,
                        target_chunk_size=config.target_chunk_size,
                        overlap=config.overlap,
                        parser_name=document.parser_name,
                    ),
                )
            )
        )
    return chunks


def _build_index(config: RetrievalEvalConfig) -> VectorIndex:
    index_config = IndexConfig(backend_name=config.index_backend)
    if config.index_backend == "lexical_in_memory":
        return LexicalInMemoryIndex(index_config)
    if config.index_backend == "embedding_in_memory":
        embedding_provider = create_embedding_provider(
            EmbeddingConfig(
                provider_name=config.embedding_provider,
                model_name=config.embedding_model,
                extra_options=config.embedding_options,
            )
        )
        return EmbeddingInMemoryIndex(
            embedding_provider=embedding_provider,
            config=index_config,
        )
    raise ValueError(f"Unsupported retrieval index: {config.index_backend}")


def _build_reranker(config: RetrievalEvalConfig) -> BaseRerankerAdapter | None:
    if not config.reranker_enabled:
        return None
    if config.reranker_mode != "python_module":
        raise ValueError(f"Unsupported reranker mode: {config.reranker_mode}")
    reranker = ExistingRerankerBridge(
        ExistingRerankerBridgeConfig(
            mode=config.reranker_mode,
            entrypoint=config.reranker_entrypoint,
            extra_options=config.reranker_options,
        )
    )
    reranker.healthcheck()
    return reranker


def _parsed_document_paths(parsed_documents_dir: Path) -> list[Path]:
    if not parsed_documents_dir.exists():
        raise FileNotFoundError(f"Parsed documents directory not found: {parsed_documents_dir}")
    direct = sorted(parsed_documents_dir.glob("*.json"))
    nested = sorted(parsed_documents_dir.glob("*/*.json"))
    return [path for path in [*direct, *nested] if path.name != "run_summary.json"]


def _load_queries(path: Path) -> list[EvaluationQuery]:
    queries = [
        EvaluationQuery(
            query_id=str(payload["query_id"]),
            query_text=str(payload["query_text"]),
            metadata=dict(payload.get("metadata", {})),
        )
        for payload in _read_jsonl(path)
    ]
    if not queries:
        raise ValueError(f"Query set is empty: {path}")
    return queries


def _load_relevance_labels(path: Path | None) -> list[RelevanceLabel]:
    if path is None:
        return []
    return [
        RelevanceLabel(
            query_id=str(payload["query_id"]),
            chunk_id=str(payload["chunk_id"]),
            grade=int(payload["grade"]),
            rationale=payload.get("rationale"),
            source=str(payload.get("source", "manual")),
        )
        for payload in _read_jsonl(path)
    ]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"JSONL file not found: {path}")
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            rows.append(json.loads(stripped))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSONL at {path}:{line_number}") from exc
    return rows


def _resolve_required_path(
    raw_path: str | None,
    config_dir: Path,
    field_name: str,
) -> Path:
    if not raw_path:
        raise ValueError(f"Missing required config field: {field_name}")
    return resolve_path(raw_path, config_dir)


def _resolve_optional_path(raw_path: str | None, config_dir: Path) -> Path | None:
    if not raw_path:
        return None
    return resolve_path(raw_path, config_dir)


def _list_value(value: Any, default: list[str]) -> list[str]:
    if value is None:
        return default
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value]


def _single_value(values: set[str], fallback: str) -> str:
    if len(values) == 1:
        return next(iter(values))
    return fallback


def main(argv: Sequence[str] | None = None) -> int:
    """Run retrieval evaluation from the command line."""

    args = build_parser().parse_args(argv)
    summary = run_retrieval_eval_from_file(
        config_path=args.config,
        query_set_override=args.query_set,
        labels_override=args.labels,
        parsed_documents_override=args.parsed_documents,
        output_dir_override=args.output_dir,
    )
    print(
        "retrieval evaluation completed. "
        f"queries={summary['query_count']} "
        f"chunks={summary['chunk_count']} "
        f"run_dir={summary['run_dir']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

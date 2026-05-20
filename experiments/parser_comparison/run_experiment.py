"""Runnable entrypoint for parser comparison experiments."""

from __future__ import annotations

import argparse
import difflib
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.artifacts import ensure_directory, write_json, write_parsed_document
from src.config_loader import load_yaml_config, resolve_path
from src.parsers import create_parser
from src.parsers.schemas import ParseRequest, ParserConfig
from src.schemas import ParsedDocument


@dataclass(slots=True)
class ParserComparisonConfig:
    """Materialized parser comparison configuration."""

    config_path: Path
    run_name: str
    document_dir: Path
    file_glob: str
    baseline_parser: str
    candidate_parsers: list[str]
    output_dir: Path
    parse_tables: bool = True
    preserve_layout: bool = True
    emit_page_images: bool = False
    include_text_blocks: bool = True
    include_tables: bool = True
    save_parsed_documents: bool = True
    parser_options: dict[str, dict[str, Any]] = field(default_factory=dict)


def build_parser() -> argparse.ArgumentParser:
    """Build the parser comparison CLI."""

    parser = argparse.ArgumentParser(description="Parser comparison runner.")
    parser.add_argument("--config", required=True, help="Path to experiment config.")
    parser.add_argument("--documents", help="Optional override for PDF input dir.")
    parser.add_argument("--output-dir", help="Optional override for run output dir.")
    return parser


def load_experiment_config(
    config_path: str | Path,
    documents_override: str | None = None,
    output_dir_override: str | None = None,
) -> ParserComparisonConfig:
    """Load and normalize a parser comparison config file."""

    raw_config, config_dir = load_yaml_config(config_path)
    experiment = raw_config.get("experiment", {})
    inputs = raw_config.get("inputs", {})
    parser_section = raw_config.get("parser", {})
    parsers_section = raw_config.get("parsers", {})
    comparison = raw_config.get("comparison", {})
    output = raw_config.get("output", {})

    document_dir = (
        Path(documents_override).expanduser().resolve()
        if documents_override
        else resolve_path(inputs.get("document_dir", "data"), config_dir)
    )
    output_dir = (
        Path(output_dir_override).expanduser().resolve()
        if output_dir_override
        else resolve_path(output.get("run_dir", "./runs/default"), config_dir)
    )
    baseline_parser = (
        parsers_section.get("baseline") or parser_section.get("name") or "pdfplumber"
    )
    candidate_parsers = _dedupe_preserving_order(
        parsers_section.get("candidates")
        or parser_section.get("compare_against")
        or [baseline_parser]
    )
    if baseline_parser not in candidate_parsers:
        candidate_parsers.insert(0, baseline_parser)

    return ParserComparisonConfig(
        config_path=Path(config_path).expanduser().resolve(),
        run_name=experiment.get("run_name", "parser-comparison"),
        document_dir=document_dir,
        file_glob=inputs.get("file_glob", "*.pdf"),
        baseline_parser=baseline_parser,
        candidate_parsers=candidate_parsers,
        output_dir=output_dir,
        parse_tables=parser_section.get("options", {}).get("parse_tables", True),
        preserve_layout=parser_section.get("options", {}).get("preserve_layout", True),
        emit_page_images=parser_section.get("options", {}).get(
            "emit_page_images", False
        ),
        include_text_blocks=comparison.get("include_text_blocks", True),
        include_tables=comparison.get("include_tables", True),
        save_parsed_documents=comparison.get("save_parsed_documents", True),
        parser_options=raw_config.get("parser_options", {}),
    )


def run_parser_comparison(config: ParserComparisonConfig) -> dict[str, Any]:
    """Execute parser comparison across the configured document set."""

    if not config.document_dir.exists():
        raise FileNotFoundError(
            f"Document directory does not exist: {config.document_dir}"
        )

    documents = sorted(config.document_dir.glob(config.file_glob))
    if not documents:
        raise FileNotFoundError(
            f"No documents matched '{config.file_glob}' in {config.document_dir}"
        )

    run_dir = ensure_directory(config.output_dir)
    parsed_documents_dir = ensure_directory(run_dir / "parsed_documents")
    comparison_dir = ensure_directory(run_dir / "comparisons")

    run_manifest: dict[str, Any] = {
        "run_name": config.run_name,
        "config_path": str(config.config_path),
        "document_dir": str(config.document_dir),
        "file_glob": config.file_glob,
        "baseline_parser": config.baseline_parser,
        "candidate_parsers": config.candidate_parsers,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "documents": [],
    }

    for source_path in documents:
        document_id = _build_document_id(source_path, config.document_dir)
        parser_results: dict[str, dict[str, Any]] = {}

        for parser_name in config.candidate_parsers:
            parser_config = _build_parser_config(config, parser_name)
            parser = create_parser(parser_name, config=parser_config)
            parser_result = _run_single_parser(
                parser=parser,
                parser_config=parser_config,
                document_id=document_id,
                source_path=source_path,
            )

            if parser_result["status"] == "success" and config.save_parsed_documents:
                artifact_path = (
                    parsed_documents_dir / parser_name / f"{document_id}.json"
                )
                write_parsed_document(artifact_path, parser_result["document"])
                parser_result["artifact_path"] = str(artifact_path)

            parser_results[parser_name] = parser_result

        comparison_summary = build_document_comparison(
            document_id=document_id,
            source_path=source_path,
            parser_results=parser_results,
            baseline_parser=config.baseline_parser,
            include_text_blocks=config.include_text_blocks,
            include_tables=config.include_tables,
        )
        write_json(comparison_dir / f"{document_id}.json", comparison_summary)
        run_manifest["documents"].append(comparison_summary)

    run_manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
    run_summary = build_run_summary(run_manifest, run_dir)
    write_json(run_dir / "run_manifest.json", run_manifest)
    write_json(run_dir / "run_summary.json", run_summary)
    return run_summary


def run_parser_comparison_from_file(
    config_path: str | Path,
    documents_override: str | None = None,
    output_dir_override: str | None = None,
) -> dict[str, Any]:
    """Load config and run the comparison in one step."""

    config = load_experiment_config(
        config_path=config_path,
        documents_override=documents_override,
        output_dir_override=output_dir_override,
    )
    return run_parser_comparison(config)


def build_document_comparison(
    document_id: str,
    source_path: Path,
    parser_results: dict[str, dict[str, Any]],
    baseline_parser: str,
    include_text_blocks: bool,
    include_tables: bool,
) -> dict[str, Any]:
    """Create a JSON-serializable comparison summary for one document."""

    baseline_document = None
    baseline_summary = None
    if parser_results.get(baseline_parser, {}).get("status") == "success":
        baseline_document = parser_results[baseline_parser]["document"]
        baseline_summary = summarize_parsed_document(
            baseline_document,
            include_text_blocks=include_text_blocks,
            include_tables=include_tables,
        )

    parser_summaries: dict[str, Any] = {}
    for parser_name, result in parser_results.items():
        if result["status"] != "success":
            parser_summaries[parser_name] = {
                "status": result["status"],
                "error_type": result.get("error_type"),
                "error": result.get("error"),
            }
            continue

        candidate_document = result["document"]
        candidate_summary = summarize_parsed_document(
            candidate_document,
            include_text_blocks=include_text_blocks,
            include_tables=include_tables,
        )
        entry: dict[str, Any] = {
            "status": "success",
            "summary": candidate_summary,
        }
        if parser_name == baseline_parser:
            entry["comparison_to_baseline"] = None
        elif baseline_document is not None and baseline_summary is not None:
            entry["comparison_to_baseline"] = compare_documents(
                baseline_document=baseline_document,
                baseline_summary=baseline_summary,
                candidate_document=candidate_document,
                candidate_summary=candidate_summary,
            )
        else:
            entry["comparison_to_baseline"] = {
                "status": "skipped",
                "reason": f"Baseline parser '{baseline_parser}' did not succeed.",
            }
        parser_summaries[parser_name] = entry

    return {
        "document_id": document_id,
        "source_path": str(source_path),
        "baseline_parser": baseline_parser,
        "parsers": parser_summaries,
    }


def summarize_parsed_document(
    document: ParsedDocument,
    include_text_blocks: bool,
    include_tables: bool,
) -> dict[str, Any]:
    """Create a compact summary from a parsed document."""

    text_blocks = [block for page in document.pages for block in page.text_blocks]
    table_blocks = [block for page in document.pages for block in page.table_blocks]
    text_content = "\n".join(page.page_text for page in document.pages).strip()

    summary: dict[str, Any] = {
        "document_id": document.document_id,
        "parser_name": document.parser_name,
        "page_count": len(document.pages),
        "text_char_count": len(text_content),
        "warning_count": len(document.warnings),
        "warnings": document.warnings,
        "pages": [
            {
                "page_number": page.page_number,
                "text_char_count": len(page.page_text.strip()),
                "text_block_count": len(page.text_blocks),
                "table_block_count": len(page.table_blocks),
            }
            for page in document.pages
        ],
    }
    if include_text_blocks:
        summary["text_block_count"] = len(text_blocks)
    if include_tables:
        summary["table_block_count"] = len(table_blocks)
        summary["table_row_count"] = sum(block.row_count or 0 for block in table_blocks)
        summary["table_markdown_char_count"] = sum(
            len(block.markdown or "") for block in table_blocks
        )
    return summary


def compare_documents(
    baseline_document: ParsedDocument,
    baseline_summary: dict[str, Any],
    candidate_document: ParsedDocument,
    candidate_summary: dict[str, Any],
) -> dict[str, Any]:
    """Compare a candidate parser output against the baseline output."""

    baseline_text = _normalize_text(
        "\n".join(page.page_text for page in baseline_document.pages)
    )
    candidate_text = _normalize_text(
        "\n".join(page.page_text for page in candidate_document.pages)
    )
    similarity = difflib.SequenceMatcher(None, baseline_text, candidate_text).ratio()

    return {
        "status": "compared",
        "page_count_delta": candidate_summary["page_count"]
        - baseline_summary["page_count"],
        "text_char_count_delta": candidate_summary["text_char_count"]
        - baseline_summary["text_char_count"],
        "text_block_count_delta": candidate_summary.get("text_block_count", 0)
        - baseline_summary.get("text_block_count", 0),
        "table_block_count_delta": candidate_summary.get("table_block_count", 0)
        - baseline_summary.get("table_block_count", 0),
        "table_row_count_delta": candidate_summary.get("table_row_count", 0)
        - baseline_summary.get("table_row_count", 0),
        "normalized_text_similarity": round(similarity, 4),
    }


def build_run_summary(run_manifest: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    """Aggregate parser comparison results across all documents."""

    per_parser: dict[str, dict[str, Any]] = {
        parser_name: {
            "success_count": 0,
            "failure_count": 0,
            "documents": [],
        }
        for parser_name in run_manifest["candidate_parsers"]
    }

    for document_result in run_manifest["documents"]:
        document_id = document_result["document_id"]
        for parser_name, parser_result in document_result["parsers"].items():
            if parser_result["status"] == "success":
                per_parser[parser_name]["success_count"] += 1
            else:
                per_parser[parser_name]["failure_count"] += 1
            per_parser[parser_name]["documents"].append(
                {
                    "document_id": document_id,
                    "status": parser_result["status"],
                }
            )

    baseline_success = (
        per_parser.get(run_manifest["baseline_parser"], {}).get("success_count", 0) > 0
    )
    any_success = any(
        parser_stats["success_count"] > 0 for parser_stats in per_parser.values()
    )

    return {
        "run_name": run_manifest["run_name"],
        "run_dir": str(run_dir),
        "baseline_parser": run_manifest["baseline_parser"],
        "candidate_parsers": run_manifest["candidate_parsers"],
        "document_count": len(run_manifest["documents"]),
        "per_parser": per_parser,
        "has_successful_baseline": baseline_success,
        "overall_status": (
            "success"
            if baseline_success
            else "partial_success" if any_success else "error"
        ),
        "started_at": run_manifest["started_at"],
        "completed_at": run_manifest["completed_at"],
    }


def _build_document_id(source_path: Path, document_dir: Path) -> str:
    relative = source_path.relative_to(document_dir)
    return "__".join(relative.with_suffix("").parts)


def _build_parser_config(
    config: ParserComparisonConfig,
    parser_name: str,
) -> ParserConfig:
    options = dict(config.parser_options.get(parser_name, {}))
    parse_tables = bool(options.pop("parse_tables", config.parse_tables))
    preserve_layout = bool(options.pop("preserve_layout", config.preserve_layout))
    emit_page_images = bool(options.pop("emit_page_images", config.emit_page_images))
    return ParserConfig(
        parser_name=parser_name,
        parse_tables=parse_tables,
        preserve_layout=preserve_layout,
        emit_page_images=emit_page_images,
        is_baseline=parser_name == config.baseline_parser,
        extra_options=options,
    )


def _run_single_parser(
    parser: object,
    parser_config: ParserConfig,
    document_id: str,
    source_path: Path,
) -> dict[str, Any]:
    try:
        parser.validate_environment()
        document = parser.parse(
            ParseRequest(
                document_id=document_id,
                source_path=source_path,
                config=parser_config,
            )
        )
        return {
            "status": "success",
            "document": document,
        }
    except Exception as exc:
        return {
            "status": "error",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }


def _dedupe_preserving_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _normalize_text(text: str) -> str:
    return " ".join(text.split())


def main(argv: Sequence[str] | None = None) -> int:
    """Run parser comparison from the command line."""

    args = build_parser().parse_args(argv)
    summary = run_parser_comparison_from_file(
        config_path=args.config,
        documents_override=args.documents,
        output_dir_override=args.output_dir,
    )
    print(
        "Parser comparison complete. "
        f"documents={summary['document_count']} "
        f"run_dir={summary['run_dir']}"
    )
    return 0 if summary["has_successful_baseline"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

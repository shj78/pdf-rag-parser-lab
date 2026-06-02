"""Command-line entrypoints for parser lab experiments."""

from __future__ import annotations

import argparse
from collections.abc import Sequence


def _build_parser_compare_parser(subparsers: argparse._SubParsersAction) -> None:
    command = subparsers.add_parser(
        "parser-compare",
        help="Prepare a parser comparison run from a config file.",
    )
    command.add_argument("--config", required=True, help="Path to experiment config.")
    command.add_argument(
        "--documents",
        help="Optional override for the input PDF directory.",
    )
    command.add_argument(
        "--output-dir",
        help="Optional override for where comparison artifacts should be saved.",
    )
    command.set_defaults(handler=_handle_parser_compare)


def _build_chunk_compare_parser(subparsers: argparse._SubParsersAction) -> None:
    command = subparsers.add_parser(
        "chunk-compare",
        help="Prepare a chunking comparison run from a config file.",
    )
    command.add_argument("--config", required=True, help="Path to experiment config.")
    command.add_argument(
        "--parsed-documents",
        help="Optional override for already parsed document artifacts.",
    )
    command.set_defaults(handler=_handle_chunk_compare)


def _build_retrieval_eval_parser(subparsers: argparse._SubParsersAction) -> None:
    command = subparsers.add_parser(
        "retrieval-eval",
        help="Prepare a retrieval plus reranker evaluation run.",
    )
    command.add_argument("--config", required=True, help="Path to experiment config.")
    command.add_argument(
        "--query-set",
        help="Optional override for the query set path.",
    )
    command.add_argument(
        "--labels",
        help="Optional override for relevance labels path.",
    )
    command.add_argument(
        "--parsed-documents",
        help="Optional override for parsed document artifact directory.",
    )
    command.add_argument(
        "--output-dir",
        help="Optional override for where retrieval artifacts should be saved.",
    )
    command.set_defaults(handler=_handle_retrieval_eval)


def build_parser() -> argparse.ArgumentParser:
    """Build the placeholder CLI parser."""

    parser = argparse.ArgumentParser(
        prog="parser-lab",
        description=(
            "Scaffold CLI for parser comparison, chunking comparison, "
            "and retrieval evaluation experiments."
        ),
    )
    subparsers = parser.add_subparsers(dest="command")
    _build_parser_compare_parser(subparsers)
    _build_chunk_compare_parser(subparsers)
    _build_retrieval_eval_parser(subparsers)
    return parser


def _handle_parser_compare(args: argparse.Namespace) -> int:
    """Run parser comparison orchestration."""

    from experiments.parser_comparison.run_experiment import (
        run_parser_comparison_from_file,
    )

    summary = run_parser_comparison_from_file(
        config_path=args.config,
        documents_override=args.documents,
        output_dir_override=args.output_dir,
    )
    print(
        "parser comparison completed. "
        f"documents={summary['document_count']} "
        f"run_dir={summary['run_dir']}"
    )
    return 0 if summary["has_successful_baseline"] else 1


def _handle_chunk_compare(args: argparse.Namespace) -> int:
    """Placeholder handler for chunking comparison orchestration."""

    print(
        "[TODO] chunking comparison orchestration is not implemented yet. "
        f"config={args.config}"
    )
    return 0


def _handle_retrieval_eval(args: argparse.Namespace) -> int:
    """Run retrieval evaluation orchestration."""

    from experiments.retrieval_eval.run_experiment import run_retrieval_eval_from_file

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


def main(argv: Sequence[str] | None = None) -> int:
    """Run the parser lab CLI."""

    parser = build_parser()
    args = parser.parse_args(argv)

    if not hasattr(args, "handler"):
        parser.print_help()
        return 0

    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())

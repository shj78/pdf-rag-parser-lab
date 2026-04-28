"""Command-line entrypoints for experiment scaffolding.

The commands in this module deliberately stop at argument parsing and intent
description. Real execution flows should be added in later implementation
phases.
"""

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
    """Placeholder handler for parser comparison orchestration."""

    print(
        "[TODO] parser comparison orchestration is not implemented yet. "
        f"config={args.config}"
    )
    return 0


def _handle_chunk_compare(args: argparse.Namespace) -> int:
    """Placeholder handler for chunking comparison orchestration."""

    print(
        "[TODO] chunking comparison orchestration is not implemented yet. "
        f"config={args.config}"
    )
    return 0


def _handle_retrieval_eval(args: argparse.Namespace) -> int:
    """Placeholder handler for retrieval evaluation orchestration."""

    print(
        "[TODO] retrieval evaluation orchestration is not implemented yet. "
        f"config={args.config}"
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the placeholder CLI.

    TODO:
    - load YAML configs
    - dispatch into experiment modules
    - write structured run metadata
    """

    parser = build_parser()
    args = parser.parse_args(argv)

    if not hasattr(args, "handler"):
        parser.print_help()
        return 0

    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())

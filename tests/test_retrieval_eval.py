from __future__ import annotations

import json
from pathlib import Path

from experiments.retrieval_eval.run_experiment import run_retrieval_eval_from_file
from src.artifacts import read_json, write_parsed_document
from src.cli import main as cli_main
from src.schemas import ParsedDocument, ParsedPage, TableBlock, TextBlock


def test_run_retrieval_eval_from_file_writes_artifacts(tmp_path: Path) -> None:
    config_path = _write_fixture_files(tmp_path)

    summary = run_retrieval_eval_from_file(config_path)

    assert summary["query_count"] == 1
    assert summary["chunk_count"] == 2
    assert summary["scores"][0]["metric_name"] == "ndcg"
    assert (tmp_path / "out" / "chunks.json").exists()
    assert (tmp_path / "out" / "rankings.json").exists()
    evaluation_result = read_json(tmp_path / "out" / "evaluation_result.json")
    assert evaluation_result["scores"][0]["value"] == 1.0


def test_cli_retrieval_eval_runs_experiment(tmp_path: Path) -> None:
    config_path = _write_fixture_files(tmp_path)
    output_dir = tmp_path / "cli-out"

    exit_code = cli_main(
        [
            "retrieval-eval",
            "--config",
            str(config_path),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    assert read_json(output_dir / "run_summary.json")["query_count"] == 1


def test_run_retrieval_eval_supports_embedding_in_memory_backend(
    tmp_path: Path,
) -> None:
    config_path = _write_fixture_files(
        tmp_path,
        extra_retrieval_lines=[
            "  index_backend: embedding_in_memory",
            "  embedding_provider: hashing",
            "  embedding_model: hashing-token-v1",
            "  embedding_options:",
            "    dimensions: 16",
        ],
    )

    summary = run_retrieval_eval_from_file(config_path)

    assert summary["index_backend"] == "embedding_in_memory"
    assert summary["embedding_provider"] == "hashing"
    assert read_json(tmp_path / "out" / "run_summary.json")["chunk_count"] == 2


def _write_fixture_files(
    tmp_path: Path,
    *,
    extra_retrieval_lines: list[str] | None = None,
) -> Path:
    parsed_dir = tmp_path / "parsed" / "mineru"
    parsed_dir.mkdir(parents=True)
    write_parsed_document(
        parsed_dir / "doc.json",
        ParsedDocument(
            document_id="doc",
            source_path="/tmp/doc.pdf",
            parser_name="mineru",
            pages=[
                ParsedPage(
                    page_number=1,
                    text_blocks=[
                        TextBlock(
                            block_id="text-1",
                            page_number=1,
                            text="청년수당 신청 자격 안내",
                        )
                    ],
                    table_blocks=[
                        TableBlock(
                            table_id="table-1",
                            page_number=1,
                            parser_name="mineru",
                            markdown="| 회차 | 지급일 |\n| --- | --- |\n| 1회 | 4월 30일 |",
                        )
                    ],
                )
            ],
        ),
    )
    _write_jsonl(
        tmp_path / "queries.jsonl",
        [{"query_id": "q1", "query_text": "지급일"}],
    )
    _write_jsonl(
        tmp_path / "labels.jsonl",
        [
            {
                "query_id": "q1",
                "chunk_id": "doc:mineru:p1:table:2",
                "grade": 2,
            }
        ],
    )
    config_path = tmp_path / "config.yaml"
    retrieval_lines = extra_retrieval_lines or [
        "  index_backend: lexical_in_memory",
    ]
    config_path.write_text(
        "\n".join(
            [
                "experiment:",
                "  run_name: retrieval-eval-test",
                "inputs:",
                "  parsed_documents_dir: parsed",
                "  query_set_path: queries.jsonl",
                "  relevance_labels_path: labels.jsonl",
                "chunker:",
                "  name: fixed_size",
                "  options:",
                "    target_chunk_size: 80",
                "    overlap: 10",
                "retrieval:",
                *retrieval_lines,
                "  top_k: 3",
                "evaluation:",
                "  metric: ndcg",
                "  k_values: [1]",
                "output:",
                "  run_dir: out",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return config_path


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )

from __future__ import annotations

import json
import sys
from importlib import import_module
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "apps" / "parser-lab-ui"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

retrieval_helpers = import_module("views.retrieval_helpers")


def test_retrieval_eval_helpers_build_comparison_rows(
    tmp_path: Path,
    monkeypatch,
) -> None:
    baseline = _write_eval_run(
        tmp_path,
        run_name="baseline",
        score_at_1=0.25,
        score_at_10=0.5,
        reranker_enabled=False,
    )
    reranker = _write_eval_run(
        tmp_path,
        run_name="reranker",
        score_at_1=1.0,
        score_at_10=0.8,
        reranker_enabled=True,
    )
    monkeypatch.setattr(
        retrieval_helpers,
        "DEFAULT_RETRIEVAL_EVAL_RUNS_DIR",
        tmp_path / "runs",
    )

    assert retrieval_helpers.list_retrieval_eval_runs() == [reranker, baseline]

    baseline_artifacts = retrieval_helpers.load_retrieval_eval_artifacts(baseline)
    reranker_artifacts = retrieval_helpers.load_retrieval_eval_artifacts(reranker)

    display_summary = retrieval_helpers.retrieval_eval_summary(baseline_artifacts)
    assert display_summary["query_count"] == 1
    assert display_summary["label_count"] == 1
    assert display_summary["chunk_count"] == 1
    assert display_summary["top_k"] == 1

    comparison = retrieval_helpers.retrieval_eval_comparison_rows(
        [
            ("baseline", baseline_artifacts),
            ("reranker", reranker_artifacts),
        ]
    )
    assert comparison[0]["NDCG@1"] == 0.25
    assert comparison[1]["전략"] == "lexical_in_memory + reranker"

    delta = retrieval_helpers.retrieval_eval_delta_rows(
        baseline_artifacts,
        reranker_artifacts,
    )
    assert delta[0] == {
        "지표": "NDCG@1",
        "baseline": 0.25,
        "candidate": 1.0,
        "개선폭": 0.75,
    }

    diagnostic = retrieval_helpers.query_diagnostic_rows(reranker_artifacts)
    assert diagnostic[0]["첫 직접 근거"] == "1위"
    assert diagnostic[0]["판정"] == "성공"

    ranking = retrieval_helpers.ranking_rows(reranker_artifacts, query_id="q1")
    assert ranking[0]["라벨"] == 2
    assert ranking[0]["리랭크 점수"] == 0.99


def _write_eval_run(
    tmp_path: Path,
    *,
    run_name: str,
    score_at_1: float,
    score_at_10: float,
    reranker_enabled: bool,
) -> Path:
    run_dir = tmp_path / "runs" / run_name
    run_dir.mkdir(parents=True)
    labels_path = tmp_path / f"{run_name}-labels.jsonl"
    queries_path = tmp_path / f"{run_name}-queries.jsonl"

    _write_jsonl(
        labels_path,
        [
            {
                "query_id": "q1",
                "chunk_id": "doc:mineru:p1:table:1",
                "grade": 2,
                "rationale": "정답 근거",
            }
        ],
    )
    _write_jsonl(
        queries_path,
        [
            {
                "query_id": "q1",
                "query_text": "지급일은?",
                "metadata": {"question_type": "table_extraction"},
            }
        ],
    )
    _write_json(
        run_dir / "run_manifest.json",
        {
            "query_set_path": str(queries_path),
            "relevance_labels_path": str(labels_path),
        },
    )
    _write_json(
        run_dir / "run_summary.json",
        {
            "query_count": 99,
            "label_count": 99,
            "chunk_count": 99,
            "index_backend": "lexical_in_memory",
            "reranker_enabled": reranker_enabled,
            "reranker_entrypoint": "fake:rerank" if reranker_enabled else None,
            "top_k": 99,
            "scores": [
                {"metric_name": "ndcg", "k": 1, "value": score_at_1},
                {"metric_name": "ndcg", "k": 10, "value": score_at_10},
            ],
        },
    )
    _write_json(
        run_dir / "evaluation_result.json",
        {
            "query_results": {
                "q1": [
                    {"metric_name": "ndcg", "k": 1, "value": score_at_1},
                    {"metric_name": "ndcg", "k": 10, "value": score_at_10},
                ]
            }
        },
    )
    _write_json(
        run_dir / "rankings.json",
        {
            "queries": [
                {
                    "query_id": "q1",
                    "query_text": "지급일은?",
                    "results": [
                        {
                            "rank": 1,
                            "score": 0.42,
                            "rerank_score": 0.99 if reranker_enabled else None,
                            "chunk_id": "doc:mineru:p1:table:1",
                            "parser_name": "mineru",
                            "page_number": 1,
                            "metadata": {
                                "chunk_type": "table",
                                "section_title": "4월",
                                "text_preview": "4월 30일 지급",
                            },
                        }
                    ],
                }
            ]
        },
    )
    _write_json(
        run_dir / "chunks.json",
        {"chunks": [{"chunk_id": "doc:mineru:p1:table:1", "text": "4월 30일 지급"}]},
    )
    return run_dir


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )

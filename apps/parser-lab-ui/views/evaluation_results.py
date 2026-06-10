"""Retrieval evaluation comparison dashboard."""

from __future__ import annotations

from typing import Any

import streamlit as st

from views.retrieval_helpers import (
    aggregate_score_rows,
    list_retrieval_eval_runs,
    load_retrieval_eval_artifacts,
    query_diagnostic_rows,
    query_score_rows,
    query_text_for_run,
    ranking_rows,
    retrieval_eval_comparison_rows,
    retrieval_eval_delta_rows,
    retrieval_eval_summary,
)


def render_evaluation_results_page() -> None:
    """Render stored retrieval/NDCG evaluation artifacts."""

    st.subheader("검색 품질 비교")
    st.caption(
        "LLM 답변 품질이 아니라, 질문에 필요한 근거 chunk가 검색 결과 상위에 "
        "올라오는지 비교합니다. baseline과 reranker run의 NDCG@k를 나란히 봅니다."
    )

    runs = list_retrieval_eval_runs()
    if not runs:
        st.warning("아직 retrieval evaluation artifact가 없습니다.")
        return

    run_labels = [run.name for run in runs]
    selected_labels = st.multiselect(
        "비교할 run",
        options=run_labels,
        default=run_labels,
    )
    if not selected_labels:
        st.warning("비교할 run을 하나 이상 선택하세요.")
        return

    artifacts_by_label = {
        run.name: load_retrieval_eval_artifacts(run)
        for run in runs
        if run.name in selected_labels
    }
    selected_artifacts = [
        (label, artifacts_by_label[label])
        for label in selected_labels
    ]

    _render_run_comparison(selected_artifacts)
    _render_query_comparison(selected_artifacts)
    _render_run_detail(selected_artifacts)


def _render_run_comparison(
    selected_artifacts: list[tuple[str, dict[str, Any]]],
) -> None:
    st.markdown("#### Run 비교")
    comparison_rows = retrieval_eval_comparison_rows(selected_artifacts)
    st.dataframe(comparison_rows, hide_index=True, width="stretch")

    if len(selected_artifacts) < 2:
        return

    baseline_label, candidate_label = _default_baseline_candidate(selected_artifacts)
    col1, col2 = st.columns(2)
    with col1:
        baseline_label = st.selectbox(
            "baseline",
            options=[label for label, _ in selected_artifacts],
            index=_label_index(selected_artifacts, baseline_label),
        )
    with col2:
        candidate_label = st.selectbox(
            "candidate",
            options=[label for label, _ in selected_artifacts],
            index=_label_index(selected_artifacts, candidate_label),
        )

    if baseline_label == candidate_label:
        st.info("개선폭을 보려면 서로 다른 두 run을 선택하세요.")
        return

    baseline = dict(selected_artifacts)[baseline_label]
    candidate = dict(selected_artifacts)[candidate_label]
    delta_rows = retrieval_eval_delta_rows(baseline, candidate)
    if not delta_rows:
        return

    st.markdown("#### 개선폭")
    metric_cols = st.columns(len(delta_rows))
    for col, row in zip(metric_cols, delta_rows, strict=False):
        col.metric(
            str(row["지표"]),
            f"{float(row['candidate']):.3f}",
            f"{float(row['개선폭']):+.3f}",
        )
    with st.expander("개선폭 표"):
        st.dataframe(delta_rows, hide_index=True, width="stretch")


def _render_query_comparison(
    selected_artifacts: list[tuple[str, dict[str, Any]]],
) -> None:
    rows: list[dict[str, Any]] = []
    for label, artifacts in selected_artifacts:
        for row in query_diagnostic_rows(artifacts):
            rows.append(
                {
                    "run": label,
                    "판정": row["판정"],
                    "질문 ID": row["질문 ID"],
                    "유형": row["유형"],
                    "NDCG@1": row["NDCG@1"],
                    "NDCG@5": row["NDCG@5"],
                    "NDCG@10": row["NDCG@10"],
                    "첫 직접 근거": row["첫 직접 근거"],
                    "질문": row["질문"],
                }
            )
    if not rows:
        return

    st.markdown("#### 질문별 비교")
    st.dataframe(rows, hide_index=True, width="stretch")


def _render_run_detail(
    selected_artifacts: list[tuple[str, dict[str, Any]]],
) -> None:
    labels = [label for label, _ in selected_artifacts]
    detail_label = st.selectbox("상세 run", options=labels)
    artifacts = dict(selected_artifacts)[detail_label]
    summary = retrieval_eval_summary(artifacts)
    manifest = artifacts.get("manifest") or {}

    _render_run_summary(summary)
    _render_scores(artifacts)
    _render_ranking_detail(artifacts)

    with st.expander("재현 설정"):
        st.json(
            {
                "run_name": summary.get("run_name") or detail_label,
                "parsed_documents_dir": manifest.get("parsed_documents_dir"),
                "query_set_path": manifest.get("query_set_path"),
                "relevance_labels_path": manifest.get("relevance_labels_path"),
                "filters": manifest.get("filters", {}),
                "chunker_options": summary.get("chunker_options", {}),
                "index_backend": summary.get("index_backend"),
                "reranker_enabled": summary.get("reranker_enabled"),
                "reranker_entrypoint": summary.get("reranker_entrypoint"),
            }
        )


def _render_run_summary(summary: dict[str, Any]) -> None:
    cols = st.columns(5)
    cols[0].metric("평가 질문", summary.get("query_count", 0))
    cols[1].metric("정답 근거 라벨", summary.get("label_count", 0))
    cols[2].metric("검색 대상 chunk", summary.get("chunk_count", 0))
    cols[3].metric("검색 방식", _strategy_label(summary))
    cols[4].metric("검색 후보", f"top-{summary.get('top_k', '-')}")


def _render_scores(artifacts: dict[str, Any]) -> None:
    rows = aggregate_score_rows(artifacts)
    if not rows:
        return

    st.markdown("#### 선택 run 전체 점수")
    metric_cols = st.columns(len(rows))
    for col, row in zip(metric_cols, rows, strict=False):
        metric = str(row["지표"])
        col.metric(metric.upper(), f"{float(row['점수']):.3f}")
        col.caption(_metric_caption(metric))


def _render_ranking_detail(artifacts: dict[str, Any]) -> None:
    diagnostic_rows = query_diagnostic_rows(artifacts)
    if not diagnostic_rows:
        return

    query_options = {
        f"{row['판정']} · {row['질문 ID']} · {row['질문'][:42]}": str(row["질문 ID"])
        for row in diagnostic_rows
    }
    selected_query_label = st.selectbox("랭킹 상세", options=list(query_options))
    selected_query_id = query_options[selected_query_label]
    query_text = query_text_for_run(artifacts, selected_query_id)
    if query_text:
        st.markdown(f"**질문:** {query_text}")

    st.caption("라벨 2는 직접 정답 근거, 라벨 1은 보조 근거, 빈 라벨은 오답 또는 무관 chunk입니다.")
    st.dataframe(
        ranking_rows(artifacts, query_id=selected_query_id),
        hide_index=True,
        width="stretch",
    )

    with st.expander("선택 run query별 원본 NDCG 표"):
        st.dataframe(query_score_rows(artifacts), hide_index=True, width="stretch")


def _default_baseline_candidate(
    selected_artifacts: list[tuple[str, dict[str, Any]]],
) -> tuple[str, str]:
    baseline = selected_artifacts[0][0]
    candidate = selected_artifacts[-1][0]
    for label, artifacts in selected_artifacts:
        summary = retrieval_eval_summary(artifacts)
        if not summary.get("reranker_enabled"):
            baseline = label
        if summary.get("reranker_enabled"):
            candidate = label
    return baseline, candidate


def _label_index(
    selected_artifacts: list[tuple[str, dict[str, Any]]],
    label: str,
) -> int:
    labels = [candidate_label for candidate_label, _ in selected_artifacts]
    return labels.index(label) if label in labels else 0


def _strategy_label(summary: dict[str, Any]) -> str:
    backend = str(summary.get("index_backend") or "-")
    if summary.get("reranker_enabled"):
        return "lexical + reranker" if backend == "lexical_in_memory" else f"{backend} + reranker"
    if backend == "lexical_in_memory":
        return "lexical"
    if backend == "embedding_in_memory":
        return "embedding"
    return backend


def _metric_caption(metric: str) -> str:
    captions = {
        "ndcg@1": "첫 결과 품질",
        "ndcg@3": "상위 3개 순위 품질",
        "ndcg@5": "상위 5개 순위 품질",
        "ndcg@10": "상위 10개 순위 품질",
    }
    return captions.get(metric.lower(), "순위 품질")

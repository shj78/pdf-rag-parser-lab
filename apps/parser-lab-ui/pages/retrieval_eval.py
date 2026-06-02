"""검색 평가 화면."""

from __future__ import annotations

import streamlit as st

from pages.retrieval_helpers import (
    chunks_to_rows,
    list_parser_runs,
    load_chunks_from_run,
    results_to_answer_draft,
    results_to_rows,
    search_chunks,
    summarize_run_content,
)

DEFAULT_QUERY = "주요 일정 표에서 회차별 지급일과 자기성장기록서 작성 기간을 정리해줘."


def render_retrieval_eval_page() -> None:
    """파서 산출물 기반 로컬 검색 평가 화면을 렌더링한다."""

    st.subheader("검색 평가")
    st.info(
        "파서 결과를 chunk로 나눈 뒤 질문과 가까운 근거 chunk를 찾는 화면입니다. "
        "현재는 QA 답변 생성이 아니라 파서 산출물이 검색 근거로 쓸 수 있는지 "
        "확인하는 로컬 MVP입니다."
    )

    runs = list_parser_runs()
    if not runs:
        st.warning("먼저 파서 비교를 실행해 parsed document artifact를 생성하세요.")
        return

    run_labels = [run.name for run in runs]
    selected_run_label = st.selectbox("파서 비교 실행 결과", options=run_labels)
    selected_run = runs[run_labels.index(selected_run_label)]

    col1, col2, col3 = st.columns(3)
    with col1:
        chunk_size = st.number_input("chunk 크기", min_value=100, value=800, step=100)
    with col2:
        overlap = st.number_input("overlap", min_value=0, value=120, step=20)
    with col3:
        top_k = st.number_input("top-k", min_value=1, max_value=20, value=5)

    query = st.text_area("질문", value=DEFAULT_QUERY, height=90)
    chunks = load_chunks_from_run(
        selected_run,
        target_chunk_size=int(chunk_size),
        overlap=int(overlap),
    )
    summary_rows = summarize_run_content(selected_run)

    st.caption(f"생성된 chunk: {len(chunks)}개")
    with st.expander("선택한 실행 결과 내용 요약", expanded=not chunks):
        st.dataframe(summary_rows, hide_index=True, width="stretch")

    if not chunks:
        st.warning(
            "이 실행 결과에는 검색 가능한 텍스트/표 내용이 없습니다. "
            "현재 안내책자 PDF는 pdfplumber, PyMuPDF, OpenDataLoader local 조합에서 "
            "텍스트가 거의 추출되지 않아 검색 평가를 할 수 없습니다. "
            "MinerU 또는 OpenDataLoader hybrid처럼 실제 텍스트/표를 추출한 실행 결과를 "
            "선택해야 검색 결과가 나옵니다."
        )
        return

    if chunks:
        with st.expander("chunk 미리보기"):
            st.dataframe(chunks_to_rows(chunks[:50]), hide_index=True, width="stretch")

    if st.button("검색 실행", type="primary"):
        results = search_chunks(
            chunks,
            query=query,
            top_k=int(top_k),
        )
        if not results:
            st.warning("검색 결과가 없습니다. 파서가 텍스트/표를 추출했는지 확인하세요.")
            return

        st.subheader("QA 답변 초안")
        st.markdown(results_to_answer_draft(results))

        st.subheader("검색 결과")
        st.dataframe(results_to_rows(results), hide_index=True, width="stretch")
        st.caption(
            "점수는 토큰 겹침 기반 임시 점수입니다. 의미 기반 검색 품질 평가는 "
            "임베딩 index와 relevance label이 붙은 뒤 진행합니다."
        )

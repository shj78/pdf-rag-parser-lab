"""메타데이터 필터링 화면."""

from __future__ import annotations

import streamlit as st

from src.schemas import Chunk
from views.retrieval_helpers import (
    chunks_to_rows,
    list_parser_runs,
    load_chunks_from_run,
    results_to_rows,
    search_chunks,
    summarize_run_content,
)

DEFAULT_QUERY = "자기성장기록서 작성 기간과 회차별 일정을 찾아줘."


def render_metadata_filtering_page() -> None:
    """검색 범위를 메타데이터로 좁히는 실험 화면을 렌더링한다."""

    st.subheader("메타데이터 필터링")
    st.info(
        "파서가 만든 chunk에 붙은 파서명, 페이지, 유형, 표 여부를 기준으로 "
        "검색 범위를 좁히는 화면입니다. 같은 질문이라도 어떤 파서/페이지/표 chunk가 "
        "근거 검색에 유리한지 확인할 때 사용합니다."
    )

    runs = list_parser_runs()
    if not runs:
        st.warning("먼저 파서 비교를 실행해 parsed document artifact를 생성하세요.")
        return

    run_labels = [run.name for run in runs]
    selected_run_label = st.selectbox("파서 비교 실행 결과", options=run_labels)
    selected_run = runs[run_labels.index(selected_run_label)]

    chunks = load_chunks_from_run(
        selected_run,
        target_chunk_size=800,
        overlap=120,
    )
    summary_rows = summarize_run_content(selected_run)
    with st.expander("선택한 실행 결과 내용 요약", expanded=not chunks):
        st.dataframe(summary_rows, hide_index=True, width="stretch")

    if not chunks:
        st.warning(
            "이 실행 결과에서 검색 가능한 chunk가 생성되지 않았습니다. "
            "메타데이터 필터링은 검색할 chunk가 있어야 동작합니다. "
            "현재 안내책자 PDF는 일부 파서 조합에서 텍스트가 0자에 가깝게 추출되므로, "
            "MinerU 또는 OpenDataLoader hybrid 실행 결과를 만든 뒤 다시 선택하세요."
        )
        return

    parser_options = ["전체", *sorted({chunk.parser_name for chunk in chunks})]
    type_options = ["전체", *sorted({chunk.chunk_type for chunk in chunks})]

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        parser_name = st.selectbox("파서", options=parser_options)
    with col2:
        chunk_type = st.selectbox("chunk 유형", options=type_options)
    with col3:
        page_number = st.number_input("페이지", min_value=0, value=0)
    with col4:
        table_only = st.checkbox("표 chunk만")

    filters = _build_filters(
        parser_name=parser_name,
        chunk_type=chunk_type,
        page_number=int(page_number),
        table_only=table_only,
    )
    filtered_chunks = [
        chunk for chunk in chunks if _chunk_matches_ui_filters(chunk, filters)
    ]

    st.caption(f"전체 chunk: {len(chunks)}개 / 필터 적용 후: {len(filtered_chunks)}개")
    st.dataframe(chunks_to_rows(filtered_chunks[:100]), hide_index=True, width="stretch")

    query = st.text_area("질문", value=DEFAULT_QUERY, height=90)
    top_k = st.number_input("top-k", min_value=1, max_value=20, value=5)

    if st.button("필터 적용 검색 실행", type="primary"):
        results = search_chunks(
            chunks,
            query=query,
            top_k=int(top_k),
            filters=filters,
        )
        if not results:
            st.warning("필터 조건에서 검색 결과가 없습니다.")
            return
        st.subheader("필터 적용 검색 결과")
        st.dataframe(results_to_rows(results), hide_index=True, width="stretch")


def _build_filters(
    *,
    parser_name: str,
    chunk_type: str,
    page_number: int,
    table_only: bool,
) -> dict[str, object]:
    filters: dict[str, object] = {}
    if parser_name != "전체":
        filters["parser_name"] = parser_name
    if chunk_type != "전체":
        filters["chunk_type"] = chunk_type
    if page_number > 0:
        filters["page_number"] = page_number
    if table_only:
        filters["has_table"] = True
    return filters


def _chunk_matches_ui_filters(chunk: Chunk, filters: dict[str, object]) -> bool:
    for key, value in filters.items():
        if key == "parser_name" and chunk.parser_name != value:
            return False
        if key == "chunk_type" and chunk.chunk_type != value:
            return False
        if key == "page_number" and chunk.page_number != value:
            return False
        if key == "has_table":
            has_table = chunk.chunk_type == "table" or bool(chunk.metadata.get("has_table"))
            if bool(value) != has_table:
                return False
    return True

"""Status banner component for the parser lab UI."""

from __future__ import annotations

import streamlit as st


def render_status_panel() -> None:
    """Render the current implementation status summary."""

    st.info(
        "파서 비교와 fixed-size chunk 기반 로컬 검색은 실행 가능합니다. "
        "리랭킹, NDCG 평가, LLM 답변 생성은 아직 준비 중입니다."
    )

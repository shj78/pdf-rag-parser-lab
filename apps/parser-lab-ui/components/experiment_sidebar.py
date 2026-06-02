"""Sidebar component for selecting experiment views."""

from __future__ import annotations

import streamlit as st


def render_experiment_sidebar() -> str:
    """Render a minimal navigation sidebar for experiment views."""

    st.sidebar.header("실험 화면")
    return st.sidebar.radio(
        "화면 선택",
        options=["파서 비교", "검색 평가", "메타데이터 필터링"],
    )

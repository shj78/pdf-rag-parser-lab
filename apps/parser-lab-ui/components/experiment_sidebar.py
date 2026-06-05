"""Sidebar component for selecting app views."""

from __future__ import annotations

import streamlit as st


def render_app_sidebar() -> str:
    """Render the primary app navigation."""

    st.sidebar.header("화면")
    return st.sidebar.radio(
        "화면 선택",
        options=["PDF RAG", "실험 도구"],
    )


def render_experiment_sidebar() -> str:
    """Render experiment-only navigation."""

    st.sidebar.subheader("실험 도구")
    return st.sidebar.radio(
        "도구 선택",
        options=["파서 비교", "검색 평가", "메타데이터 필터링"],
    )

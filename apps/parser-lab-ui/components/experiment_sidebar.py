"""Sidebar component for selecting experiment views."""

from __future__ import annotations

import streamlit as st


def render_experiment_sidebar() -> str:
    """Render a minimal navigation sidebar for experiment views."""

    st.sidebar.header("Lab Views")
    return st.sidebar.radio(
        "Select a section",
        options=["Parser Comparison", "Retrieval Eval", "Metadata Filtering"],
    )

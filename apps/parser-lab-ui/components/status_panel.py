"""Status banner component for the placeholder UI."""

from __future__ import annotations

import streamlit as st


def render_status_panel() -> None:
    """Render a static status summary for the scaffold stage."""

    st.info(
        "Scaffold-only mode: interfaces, schemas, and docs are ready. "
        "Implementation of parser, retrieval, reranking, and evaluation logic "
        "is intentionally deferred."
    )

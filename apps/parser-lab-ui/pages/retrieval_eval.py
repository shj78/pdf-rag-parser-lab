"""Retrieval evaluation page placeholder."""

from __future__ import annotations

import streamlit as st


def render_retrieval_eval_page() -> None:
    """Render a placeholder retrieval and reranking view."""

    st.subheader("Retrieval + Existing Reranker")
    st.write("This section is reserved for retrieval runs and NDCG summaries.")
    st.code(
        "TODO: show top-k retrieval results, reranked results, and eval charts.",
        language="text",
    )

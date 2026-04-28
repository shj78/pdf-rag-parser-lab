"""Parser comparison page placeholder."""

from __future__ import annotations

import streamlit as st


def render_parser_comparison_page() -> None:
    """Render a placeholder parser comparison view."""

    st.subheader("Parser Comparison")
    st.write("Baseline parser: `pdfplumber`")
    st.write("Alternative candidates: `pymupdf`, `opendataloader`")
    st.text_area(
        "Comparison Notes",
        value=(
            "TODO: render parsed text blocks, table blocks, and structural "
            "comparison summaries here."
        ),
        height=160,
    )

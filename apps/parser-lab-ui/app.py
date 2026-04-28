"""Minimal Streamlit scaffold for the parser comparison lab UI."""

from __future__ import annotations

import streamlit as st

from components.experiment_sidebar import render_experiment_sidebar
from components.status_panel import render_status_panel
from pages.metadata_filtering import render_metadata_filtering_page
from pages.parser_comparison import render_parser_comparison_page
from pages.retrieval_eval import render_retrieval_eval_page


def main() -> None:
    """Render the placeholder parser lab UI."""

    st.set_page_config(page_title="PDF Parser Lab", layout="wide")
    st.title("PDF Parser Lab UI")
    st.caption(
        "Placeholder UI for parser comparison, retrieval, reranker bridge, "
        "and NDCG evaluation planning."
    )

    selected_page = render_experiment_sidebar()
    render_status_panel()

    if selected_page == "Parser Comparison":
        render_parser_comparison_page()
    elif selected_page == "Retrieval Eval":
        render_retrieval_eval_page()
    else:
        render_metadata_filtering_page()


if __name__ == "__main__":
    main()

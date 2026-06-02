"""Streamlit UI for parser lab experiments."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parents[1]
for import_path in (APP_DIR, PROJECT_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))


def main() -> None:
    """Render the parser lab UI."""

    from components.experiment_sidebar import render_experiment_sidebar
    from components.status_panel import render_status_panel
    from pages.metadata_filtering import render_metadata_filtering_page
    from pages.parser_comparison import render_parser_comparison_page
    from pages.retrieval_eval import render_retrieval_eval_page

    st.set_page_config(page_title="PDF 파서 실험실", layout="wide")
    st.title("PDF 파서 실험실")
    st.caption("파서 비교 작업 공간")

    selected_page = render_experiment_sidebar()
    render_status_panel()

    if selected_page == "파서 비교":
        render_parser_comparison_page()
    elif selected_page == "검색 평가":
        render_retrieval_eval_page()
    else:
        render_metadata_filtering_page()


if __name__ == "__main__":
    main()

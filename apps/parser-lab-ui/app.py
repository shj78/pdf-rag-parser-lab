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

    from components.status_panel import render_status_panel
    from views.evaluation_results import render_evaluation_results_page
    from views.pdf_rag import render_pdf_rag_page

    st.set_page_config(page_title="PDF RAG", layout="wide")
    st.title("PDF RAG")

    render_status_panel()
    rag_tab, eval_tab = st.tabs(["PDF 질문", "검색 품질 비교"])
    with rag_tab:
        render_pdf_rag_page()
    with eval_tab:
        render_evaluation_results_page()


if __name__ == "__main__":
    main()

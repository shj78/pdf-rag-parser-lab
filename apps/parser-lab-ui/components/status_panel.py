"""Status banner component for the parser lab UI."""

from __future__ import annotations

import streamlit as st


def render_status_panel() -> None:
    """Render the current implementation status summary."""

    st.info(
        "PDF를 선택하고 파서를 고른 뒤 질문할 수 있습니다. "
        "기본 답변은 검색 근거 기반이며, OpenAI 또는 Ollama 설정이 있으면 LLM 답변 생성도 사용할 수 있습니다."
    )

"""Metadata filtering page placeholder."""

from __future__ import annotations

import streamlit as st


def render_metadata_filtering_page() -> None:
    """Render a placeholder metadata filtering view."""

    st.subheader("Metadata Filtering")
    st.write(
        "Planned filter fields: `chunk_type`, `section_title`, `heading_path`, "
        "and `has_table`."
    )
    st.warning("TODO: add filter controls and filtered retrieval comparisons.")

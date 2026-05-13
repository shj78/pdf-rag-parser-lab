"""Shared helpers for parser adapters."""

from __future__ import annotations

from typing import Any

from src.schemas import BoundingBox


def build_bbox(
    x0: float | None,
    y0: float | None,
    x1: float | None,
    y1: float | None,
) -> BoundingBox | None:
    """Build a BoundingBox when coordinates are available."""

    if None in (x0, y0, x1, y1):
        return None
    return BoundingBox(x0=float(x0), y0=float(y0), x1=float(x1), y1=float(y1))


def normalize_cell(value: Any) -> str:
    """Normalize a raw table cell into a comparison-friendly string."""

    if value is None:
        return ""
    return str(value).replace("\r\n", "\n").replace("\r", "\n").strip()


def table_rows_to_markdown(rows: list[list[Any]]) -> str | None:
    """Convert table rows into a simple markdown table string."""

    normalized_rows = [
        [normalize_cell(cell) for cell in row]
        for row in rows
        if any(normalize_cell(cell) for cell in row)
    ]
    if not normalized_rows:
        return None

    width = max(len(row) for row in normalized_rows)
    padded_rows = [row + [""] * (width - len(row)) for row in normalized_rows]
    header = padded_rows[0]
    separator = ["---"] * width
    body = padded_rows[1:]
    markdown_rows = [_format_markdown_row(header), _format_markdown_row(separator)]
    markdown_rows.extend(_format_markdown_row(row) for row in body)
    return "\n".join(markdown_rows)


def _format_markdown_row(row: list[str]) -> str:
    escaped = [cell.replace("|", "\\|").replace("\n", "<br>") for cell in row]
    return f"| {' | '.join(escaped)} |"

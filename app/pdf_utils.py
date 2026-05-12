"""Utilities for robust PDF text extraction with pdfplumber."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Sequence

from .exceptions import PDFProcessingError

if TYPE_CHECKING:
    import pdfplumber

logger = logging.getLogger(__name__)

_MIN_BBOX_SPAN = 1e-6


def extract_text_from_pdf(file_path: str) -> str:
    """Extract text from a PDF and append markdown-rendered tables."""

    texts: list[str] = []

    try:
        import pdfplumber

        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text, tables = _extract_page_content(page)

                if page_text:
                    texts.append(page_text)

                for rows in tables:
                    markdown = _table_rows_to_markdown(rows)
                    if markdown:
                        texts.append(markdown)
    except ImportError as e:
        raise PDFProcessingError(
            "PDF 처리에 필요한 라이브러리가 설치되어 있지 않습니다.", detail=str(e)
        ) from e
    except PDFProcessingError:
        raise
    except Exception as e:
        error_msg = str(e).lower()
        if "password" in error_msg or "encrypted" in error_msg:
            raise PDFProcessingError(
                "비밀번호로 보호된 PDF는 처리할 수 없습니다.", detail=str(e)
            ) from e
        raise PDFProcessingError(
            "PDF 파일을 열거나 읽는 중 오류가 발생했습니다. 파일이 손상되었을 수 있습니다.",
            detail=str(e),
        ) from e

    full_text = "\n\n".join(texts).strip()

    if not full_text:
        raise PDFProcessingError(
            "PDF에서 텍스트를 추출할 수 없습니다. 이미지 전용 PDF이거나 내용이 없는 파일입니다."
        )

    return full_text


def _extract_page_content(page: Any) -> tuple[str, list[list[list[str | None]]]]:
    """Extract regular page text and tables while tolerating loose table bboxes."""

    table_objects = page.find_tables()
    table_rows = [table.extract() for table in table_objects]

    if not table_objects:
        return page.extract_text() or "", table_rows

    non_table_page = page
    for table in table_objects:
        safe_bbox = _clamp_bbox_to_page(table.bbox, page.bbox)
        if safe_bbox is None:
            logger.warning(
                "Skipping degenerate table bbox on page %s: table_bbox=%s page_bbox=%s",
                getattr(page, "page_number", "?"),
                table.bbox,
                page.bbox,
            )
            continue
        try:
            non_table_page = non_table_page.outside_bbox(safe_bbox)
        except ValueError as e:
            logger.warning(
                "Skipping invalid table bbox on page %s after clamping: table_bbox=%s clamped_bbox=%s page_bbox=%s error=%s",
                getattr(page, "page_number", "?"),
                table.bbox,
                safe_bbox,
                page.bbox,
                e,
            )

    return non_table_page.extract_text() or "", table_rows


def _clamp_bbox_to_page(
    bbox: Sequence[float], page_bbox: Sequence[float]
) -> tuple[float, float, float, float] | None:
    """Clamp a table bbox so pdfplumber can safely apply `outside_bbox`."""

    x0, y0, x1, y1 = (float(value) for value in bbox)
    px0, py0, px1, py1 = (float(value) for value in page_bbox)

    clamped = (
        min(max(x0, px0), px1),
        min(max(y0, py0), py1),
        min(max(x1, px0), px1),
        min(max(y1, py0), py1),
    )

    if clamped[2] - clamped[0] <= _MIN_BBOX_SPAN:
        return None
    if clamped[3] - clamped[1] <= _MIN_BBOX_SPAN:
        return None

    return clamped


def _table_rows_to_markdown(rows: list[list[str | None]] | None) -> str:
    if not rows:
        return ""

    lines: list[str] = []
    for index, row in enumerate(rows):
        cells = [str(cell).strip() if cell is not None else "" for cell in row]
        lines.append("| " + " | ".join(cells) + " |")
        if index == 0:
            lines.append("| " + " | ".join(["---"] * len(cells)) + " |")
    return "\n".join(lines)

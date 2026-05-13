"""Baseline parser implementation backed by pdfplumber."""

from __future__ import annotations

from collections.abc import Iterable
from importlib import import_module

from src.schemas import ParsedDocument, ParsedPage, TableBlock, TextBlock

from .base import BasePDFParser
from .helpers import build_bbox, normalize_cell, table_rows_to_markdown
from .schemas import ParseRequest, ParserDescriptor


class PDFPlumberBaselineParser(BasePDFParser):
    """Baseline parser using pdfplumber.

    This adapter is intentionally marked as the baseline because pdfplumber has
    already been tried in the existing system and exposed limitations around
    table accuracy and structure preservation.
    """

    name = "pdfplumber"
    is_baseline = True

    @classmethod
    def describe(cls) -> ParserDescriptor:
        return ParserDescriptor(
            name=cls.name,
            display_name="pdfplumber Baseline",
            description=(
                "Reference parser used to compare alternative PDF extraction "
                "approaches against an existing baseline."
            ),
            is_baseline=True,
            strengths=[
                "Known behavior from the existing PDF RAG pipeline",
                "Useful baseline for text and table comparison",
            ],
            known_limitations=[
                "Table extraction fidelity needs closer evaluation",
                "Layout and structure preservation are known concerns",
            ],
        )

    def validate_environment(self) -> None:
        import_module("pdfplumber")

    def parse(self, request: ParseRequest) -> ParsedDocument:
        """Parse a PDF with pdfplumber and map into the common schema."""

        self.validate_environment()
        pdfplumber = import_module("pdfplumber")

        pages: list[ParsedPage] = []
        warnings: list[str] = []

        with pdfplumber.open(str(request.source_path)) as pdf:
            for page_index, page in enumerate(pdf.pages, start=1):
                text_blocks = self._extract_text_blocks(
                    document_id=request.document_id,
                    page_number=page_index,
                    words=page.extract_words(use_text_flow=True),
                )
                page_text = (
                    page.extract_text(layout=request.config.preserve_layout) or ""
                )
                table_blocks, table_warnings = self._extract_table_blocks(
                    document_id=request.document_id,
                    page_number=page_index,
                    page=page,
                )
                warnings.extend(table_warnings)
                if not page_text.strip() and text_blocks:
                    page_text = "\n".join(block.text for block in text_blocks)

                pages.append(
                    ParsedPage(
                        page_number=page_index,
                        page_text=page_text,
                        text_blocks=text_blocks,
                        table_blocks=(
                            table_blocks if request.config.parse_tables else []
                        ),
                        metadata={
                            "width": float(page.width),
                            "height": float(page.height),
                        },
                    )
                )

        return ParsedDocument(
            document_id=request.document_id,
            source_path=str(request.source_path),
            parser_name=self.name,
            pages=pages,
            metadata={
                "is_baseline": True,
                "parse_tables": request.config.parse_tables,
                "preserve_layout": request.config.preserve_layout,
            },
            warnings=warnings,
        )

    def _extract_text_blocks(
        self,
        document_id: str,
        page_number: int,
        words: Iterable[dict[str, object]],
    ) -> list[TextBlock]:
        text_blocks: list[TextBlock] = []
        sorted_words = sorted(
            words,
            key=lambda word: (
                float(word.get("top", 0.0)),
                float(word.get("x0", 0.0)),
            ),
        )
        if not sorted_words:
            return text_blocks

        line_groups: list[list[dict[str, object]]] = []
        current_group: list[dict[str, object]] = []
        current_top: float | None = None
        tolerance = 3.0

        for word in sorted_words:
            top = float(word.get("top", 0.0))
            if (
                current_group
                and current_top is not None
                and abs(top - current_top) > tolerance
            ):
                line_groups.append(current_group)
                current_group = []
                current_top = None

            current_group.append(word)
            if current_top is None:
                current_top = top
            else:
                current_top = (current_top + top) / 2

        if current_group:
            line_groups.append(current_group)

        for line_index, line_words in enumerate(line_groups, start=1):
            text = " ".join(
                str(word.get("text", "")).strip()
                for word in sorted(
                    line_words, key=lambda item: float(item.get("x0", 0.0))
                )
                if str(word.get("text", "")).strip()
            ).strip()
            if not text:
                continue

            text_blocks.append(
                TextBlock(
                    block_id=f"{document_id}:p{page_number}:text:{line_index}",
                    page_number=page_number,
                    text=text,
                    bbox=build_bbox(
                        min(float(word.get("x0", 0.0)) for word in line_words),
                        min(float(word.get("top", 0.0)) for word in line_words),
                        max(float(word.get("x1", 0.0)) for word in line_words),
                        max(float(word.get("bottom", 0.0)) for word in line_words),
                    ),
                    metadata={
                        "source": "pdfplumber.extract_words",
                        "word_count": len(line_words),
                    },
                )
            )

        return text_blocks

    def _extract_table_blocks(
        self,
        document_id: str,
        page_number: int,
        page: object,
    ) -> tuple[list[TableBlock], list[str]]:
        table_blocks: list[TableBlock] = []
        warnings: list[str] = []

        try:
            discovered = page.find_tables()
            tables = list(getattr(discovered, "tables", discovered))
        except Exception as exc:
            return [], [f"page {page_number}: table extraction failed ({exc})"]

        for table_index, table in enumerate(tables, start=1):
            try:
                rows = table.extract() or []
            except Exception as exc:
                warnings.append(
                    f"page {page_number}: table {table_index} extraction failed ({exc})"
                )
                rows = []

            normalized_rows = [
                [normalize_cell(cell) for cell in row]
                for row in rows
                if row is not None
            ]
            table_blocks.append(
                TableBlock(
                    table_id=f"{document_id}:p{page_number}:table:{table_index}",
                    page_number=page_number,
                    parser_name=self.name,
                    row_count=len(normalized_rows) or None,
                    col_count=max((len(row) for row in normalized_rows), default=0)
                    or None,
                    markdown=table_rows_to_markdown(normalized_rows),
                    raw_cells=normalized_rows,
                    bbox=build_bbox(*getattr(table, "bbox", (None, None, None, None))),
                    metadata={
                        "source": "pdfplumber.find_tables",
                    },
                )
            )

        return table_blocks, warnings

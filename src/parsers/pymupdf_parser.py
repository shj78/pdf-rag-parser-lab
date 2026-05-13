"""Alternative parser implementation backed by PyMuPDF."""

from __future__ import annotations

from importlib import import_module

from src.schemas import ParsedDocument, ParsedPage, TableBlock, TextBlock

from .base import BasePDFParser
from .helpers import build_bbox, normalize_cell, table_rows_to_markdown
from .schemas import ParseRequest, ParserDescriptor


class PyMuPDFParser(BasePDFParser):
    """Parser adapter for PyMuPDF-based extraction."""

    name = "pymupdf"

    @classmethod
    def describe(cls) -> ParserDescriptor:
        return ParserDescriptor(
            name=cls.name,
            display_name="PyMuPDF Parser",
            description=(
                "Alternative parser candidate for comparing text extraction, "
                "layout preservation, and table-adjacent structure handling."
            ),
            strengths=[
                "Potentially stronger layout access primitives",
                "Useful alternative to baseline parser behavior",
            ],
            known_limitations=[
                "Table extraction strategy still needs to be designed",
            ],
        )

    def validate_environment(self) -> None:
        import_module("fitz")

    def parse(self, request: ParseRequest) -> ParsedDocument:
        """Parse a PDF with PyMuPDF and map into the common schema."""

        self.validate_environment()
        fitz = import_module("fitz")

        pages: list[ParsedPage] = []
        warnings: list[str] = []

        with fitz.open(str(request.source_path)) as document:
            for page_index, page in enumerate(document, start=1):
                text_blocks = self._extract_text_blocks(
                    document_id=request.document_id,
                    page_number=page_index,
                    raw_blocks=page.get_text("blocks"),
                )
                table_blocks, table_warnings = self._extract_table_blocks(
                    document_id=request.document_id,
                    page_number=page_index,
                    page=page,
                )
                warnings.extend(table_warnings)
                page_text = page.get_text() or ""

                pages.append(
                    ParsedPage(
                        page_number=page_index,
                        page_text=page_text.strip(),
                        text_blocks=text_blocks,
                        table_blocks=(
                            table_blocks if request.config.parse_tables else []
                        ),
                        metadata={
                            "width": float(page.rect.width),
                            "height": float(page.rect.height),
                        },
                    )
                )

        return ParsedDocument(
            document_id=request.document_id,
            source_path=str(request.source_path),
            parser_name=self.name,
            pages=pages,
            metadata={
                "parse_tables": request.config.parse_tables,
                "preserve_layout": request.config.preserve_layout,
            },
            warnings=warnings,
        )

    def _extract_text_blocks(
        self,
        document_id: str,
        page_number: int,
        raw_blocks: list[tuple[object, ...]],
    ) -> list[TextBlock]:
        text_blocks: list[TextBlock] = []

        for block_index, raw_block in enumerate(raw_blocks, start=1):
            if len(raw_block) < 5:
                continue

            x0, y0, x1, y1 = raw_block[0:4]
            text = str(raw_block[4]).strip()
            block_type = int(raw_block[6]) if len(raw_block) > 6 else 0
            if block_type != 0 or not text:
                continue

            text_blocks.append(
                TextBlock(
                    block_id=f"{document_id}:p{page_number}:text:{block_index}",
                    page_number=page_number,
                    text=text,
                    bbox=build_bbox(x0, y0, x1, y1),
                    metadata={
                        "source": "pymupdf.get_text(blocks)",
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
            return [], [f"page {page_number}: table detection unavailable ({exc})"]

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
                        "source": "pymupdf.find_tables",
                    },
                )
            )

        return table_blocks, warnings

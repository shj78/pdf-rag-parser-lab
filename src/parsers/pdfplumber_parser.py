"""Baseline parser scaffold backed by pdfplumber."""

from __future__ import annotations

from src.schemas import ParsedDocument

from .base import BasePDFParser
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

    def parse(self, request: ParseRequest) -> ParsedDocument:
        """Parse a PDF with pdfplumber and map into the common schema.

        TODO:
        - wire actual pdfplumber extraction
        - record baseline-specific table metadata
        - expose failure cases for comparison runs
        """

        raise NotImplementedError("TODO: implement the pdfplumber baseline parser.")

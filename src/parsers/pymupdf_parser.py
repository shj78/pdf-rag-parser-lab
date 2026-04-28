"""Alternative parser scaffold backed by PyMuPDF."""

from __future__ import annotations

from src.schemas import ParsedDocument

from .base import BasePDFParser
from .schemas import ParseRequest, ParserDescriptor


class PyMuPDFParser(BasePDFParser):
    """Parser adapter placeholder for PyMuPDF-based extraction."""

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

    def parse(self, request: ParseRequest) -> ParsedDocument:
        """Parse a PDF with PyMuPDF and map into the common schema.

        TODO:
        - define block extraction strategy
        - determine how table candidates should be represented
        - normalize output to ParsedDocument
        """

        raise NotImplementedError("TODO: implement the PyMuPDF parser adapter.")

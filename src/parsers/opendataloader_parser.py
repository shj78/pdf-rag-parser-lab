"""Placeholder adapter for an OpenDataLab-style parser candidate."""

from __future__ import annotations

from src.schemas import ParsedDocument

from .base import BasePDFParser
from .schemas import ParseRequest, ParserDescriptor


class OpenDataLoaderParser(BasePDFParser):
    """Parser adapter placeholder for a future OpenDataLab integration.

    The exact upstream library, package name, or service boundary should be
    confirmed before implementation. This scaffold exists so experiment code can
    reserve a stable adapter slot ahead of that decision.
    """

    name = "opendataloader"

    @classmethod
    def describe(cls) -> ParserDescriptor:
        return ParserDescriptor(
            name=cls.name,
            display_name="OpenDataLab Parser",
            description=(
                "Reserved adapter slot for a future OpenDataLab-style parser "
                "integration."
            ),
            strengths=[
                "Provides an explicit comparison slot for a third parser family",
            ],
            known_limitations=[
                "Upstream dependency and execution model are not finalized yet",
            ],
        )

    def parse(self, request: ParseRequest) -> ParsedDocument:
        """Parse a PDF with a future OpenDataLab adapter.

        TODO:
        - confirm dependency or service contract
        - define adapter input and output normalization
        - capture parser-specific table metadata
        """

        raise NotImplementedError(
            "TODO: implement the OpenDataLab parser adapter."
        )

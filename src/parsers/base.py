"""Abstract base interface for PDF parsers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from src.schemas import ParsedDocument

from .schemas import ParseRequest, ParserConfig, ParserDescriptor


class BasePDFParser(ABC):
    """Base contract for parser adapters used in comparison experiments."""

    name: ClassVar[str] = "base"
    is_baseline: ClassVar[bool] = False

    def __init__(self, config: ParserConfig | None = None) -> None:
        self.config = config or ParserConfig(
            parser_name=self.name,
            is_baseline=self.is_baseline,
        )

    @classmethod
    @abstractmethod
    def describe(cls) -> ParserDescriptor:
        """Return a descriptor for experiment UIs and registries."""

    @abstractmethod
    def parse(self, request: ParseRequest) -> ParsedDocument:
        """Parse a PDF into the common document schema.

        TODO:
        - implement parser-specific extraction
        - map raw outputs into ParsedDocument / ParsedPage / block schemas
        - preserve enough structure to compare table fidelity
        """

    def validate_environment(self) -> None:
        """Validate optional parser dependencies before execution.

        TODO: check parser-specific packages or service dependencies here.
        """


__all__ = ["BasePDFParser"]

"""Factory helpers for parser lookup and instantiation."""

from __future__ import annotations

from .base import BasePDFParser
from .mineru_parser import MinerUParser
from .opendataloader_parser import OpenDataLoaderParser
from .pdfplumber_parser import PDFPlumberBaselineParser
from .pymupdf_parser import PyMuPDFParser
from .schemas import ParserConfig, ParserDescriptor

PARSER_REGISTRY: dict[str, type[BasePDFParser]] = {
    PDFPlumberBaselineParser.name: PDFPlumberBaselineParser,
    PyMuPDFParser.name: PyMuPDFParser,
    OpenDataLoaderParser.name: OpenDataLoaderParser,
    MinerUParser.name: MinerUParser,
}


def get_parser_class(parser_name: str) -> type[BasePDFParser]:
    """Return the parser class registered for a parser name."""

    try:
        return PARSER_REGISTRY[parser_name]
    except KeyError as exc:
        available = ", ".join(sorted(PARSER_REGISTRY))
        raise ValueError(
            f"Unknown parser '{parser_name}'. Available parsers: {available}"
        ) from exc


def create_parser(
    parser_name: str,
    config: ParserConfig | None = None,
) -> BasePDFParser:
    """Instantiate a parser adapter from the registry."""

    parser_class = get_parser_class(parser_name)
    return parser_class(config=config)


def list_parser_descriptors() -> list[ParserDescriptor]:
    """Return parser descriptors for UI rendering or experiment config validation."""

    return [parser_class.describe() for parser_class in PARSER_REGISTRY.values()]


__all__ = ["PARSER_REGISTRY", "create_parser", "get_parser_class", "list_parser_descriptors"]

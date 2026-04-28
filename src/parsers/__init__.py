"""Parser interfaces and parser registry for PDF comparison experiments."""

from .factory import create_parser, get_parser_class, list_parser_descriptors

__all__ = ["create_parser", "get_parser_class", "list_parser_descriptors"]

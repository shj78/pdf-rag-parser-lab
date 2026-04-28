"""Helper signatures for metadata normalization and construction."""

from __future__ import annotations

from src.schemas import Chunk, ParsedDocument

from .schemas import ChunkMetadata, DocumentMetadata, MetadataFilterSpec


def build_document_metadata(document: ParsedDocument) -> DocumentMetadata:
    """Create document metadata from a parsed document.

    TODO:
    - normalize file names and parser identifiers
    - include extra document-level metadata as needed
    """

    raise NotImplementedError("TODO: implement document metadata construction.")


def build_chunk_metadata(chunk: Chunk, file_name: str) -> ChunkMetadata:
    """Create chunk metadata from a chunk contract.

    TODO:
    - propagate parser and heading metadata
    - detect table-linked chunks in a consistent way
    """

    raise NotImplementedError("TODO: implement chunk metadata construction.")


def normalize_filter_spec(filter_spec: MetadataFilterSpec) -> MetadataFilterSpec:
    """Normalize a metadata filter spec before retrieval usage.

    TODO:
    - define canonical handling for heading paths
    - document any parser-specific normalization rules
    """

    raise NotImplementedError("TODO: implement metadata filter normalization.")

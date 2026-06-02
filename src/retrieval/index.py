"""Vector index interfaces for retrieval experiments."""

from __future__ import annotations

import math
import re
from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from src.schemas import Chunk, RetrievalResult

from .embeddings import EmbeddingProvider, EmbeddingRequest


@dataclass(slots=True)
class IndexConfig:
    """Configuration envelope for a vector index backend."""

    backend_name: str
    namespace: str = "default"
    extra_options: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SearchRequest:
    """Query-time input for a vector index search."""

    query_id: str
    query_text: str
    top_k: int = 10
    filters: dict[str, Any] = field(default_factory=dict)


class VectorIndex(ABC):
    """Abstract interface for index build and search operations."""

    @abstractmethod
    def build(self, chunks: list[Chunk]) -> None:
        """Build or refresh the search index from chunks.

        TODO:
        - define how chunk embeddings are persisted
        - choose backend-specific storage behavior
        - log index build metadata for experiments
        """

    @abstractmethod
    def search(self, request: SearchRequest) -> list[RetrievalResult]:
        """Return initial retrieval results before reranking.

        TODO:
        - map backend scores into the shared RetrievalResult schema
        - preserve chunk metadata required for analysis
        """


class LexicalInMemoryIndex(VectorIndex):
    """Small local index using token-overlap cosine scoring.

    This is intentionally dependency-free. It is not a semantic embedding index,
    but it is useful for UI smoke tests and metadata filtering experiments.
    """

    def __init__(self, config: IndexConfig | None = None) -> None:
        self.config = config or IndexConfig(backend_name="lexical_in_memory")
        self._chunks: list[Chunk] = []
        self._vectors: dict[str, Counter[str]] = {}

    def build(self, chunks: list[Chunk]) -> None:
        self._chunks = list(chunks)
        self._vectors = {
            chunk.chunk_id: Counter(_tokenize(chunk.text)) for chunk in self._chunks
        }

    def search(self, request: SearchRequest) -> list[RetrievalResult]:
        query_vector = Counter(_tokenize(request.query_text))
        if not query_vector:
            return []

        scored: list[tuple[float, Chunk]] = []
        for chunk in self._chunks:
            if not _matches_filters(chunk, request.filters):
                continue
            score = _sparse_cosine(
                query_vector,
                self._vectors.get(chunk.chunk_id, Counter()),
            )
            if score <= 0:
                continue
            scored.append((score, chunk))

        scored.sort(key=lambda item: item[0], reverse=True)
        results: list[RetrievalResult] = []
        for rank, (score, chunk) in enumerate(scored[: request.top_k], start=1):
            results.append(
                RetrievalResult(
                    query_id=request.query_id,
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    parser_name=chunk.parser_name,
                    score=round(score, 6),
                    rank=rank,
                    page_number=chunk.page_number,
                    metadata={
                        **chunk.metadata,
                        "chunk_type": chunk.chunk_type,
                        "section_title": chunk.section_title,
                        "heading_path": chunk.heading_path,
                        "text_preview": chunk.text[:500],
                        "source_block_ids": chunk.source_block_ids,
                    },
                )
            )
        return results


class EmbeddingInMemoryIndex(VectorIndex):
    """Small local vector index using an injected embedding provider."""

    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        config: IndexConfig | None = None,
    ) -> None:
        self.embedding_provider = embedding_provider
        self.config = config or IndexConfig(backend_name="embedding_in_memory")
        self._chunks: list[Chunk] = []
        self._vectors: dict[str, list[float]] = {}

    def build(self, chunks: list[Chunk]) -> None:
        self._chunks = list(chunks)
        embeddings = self.embedding_provider.embed(
            EmbeddingRequest(
                texts=[chunk.text for chunk in self._chunks],
                input_type="document",
            )
        )
        if len(embeddings) != len(self._chunks):
            raise ValueError("embedding provider returned a mismatched vector count")
        self._vectors = {
            chunk.chunk_id: _validate_vector(vector)
            for chunk, vector in zip(self._chunks, embeddings, strict=True)
        }

    def search(self, request: SearchRequest) -> list[RetrievalResult]:
        query_embeddings = self.embedding_provider.embed(
            EmbeddingRequest(texts=[request.query_text], input_type="query")
        )
        if len(query_embeddings) != 1:
            raise ValueError("embedding provider must return exactly one query vector")
        query_vector = _validate_vector(query_embeddings[0])
        if not query_vector:
            return []

        scored: list[tuple[float, Chunk]] = []
        for chunk in self._chunks:
            if not _matches_filters(chunk, request.filters):
                continue
            score = _dense_cosine(query_vector, self._vectors.get(chunk.chunk_id, []))
            scored.append((score, chunk))

        scored.sort(key=lambda item: item[0], reverse=True)
        results: list[RetrievalResult] = []
        for rank, (score, chunk) in enumerate(scored[: request.top_k], start=1):
            results.append(
                RetrievalResult(
                    query_id=request.query_id,
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    parser_name=chunk.parser_name,
                    score=round(score, 6),
                    rank=rank,
                    page_number=chunk.page_number,
                    metadata={
                        **chunk.metadata,
                        "chunk_type": chunk.chunk_type,
                        "section_title": chunk.section_title,
                        "heading_path": chunk.heading_path,
                        "text_preview": chunk.text[:500],
                        "source_block_ids": chunk.source_block_ids,
                        "index_backend": self.config.backend_name,
                    },
                )
            )
        return results


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[0-9A-Za-z가-힣]+", text.lower())


def _sparse_cosine(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    numerator = sum(left[token] * right.get(token, 0) for token in left)
    if numerator == 0:
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def _dense_cosine(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    if len(left) != len(right):
        raise ValueError("embedding vectors must have the same dimension")
    numerator = sum(
        left_value * right_value
        for left_value, right_value in zip(left, right, strict=True)
    )
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def _validate_vector(vector: list[float]) -> list[float]:
    return [float(value) for value in vector]


def _matches_filters(chunk: Chunk, filters: dict[str, Any]) -> bool:
    for key, value in filters.items():
        if value in (None, "", [], ()):
            continue
        if key == "parser_name" and chunk.parser_name != value:
            return False
        if key == "chunk_type" and chunk.chunk_type != value:
            return False
        if key == "page_number" and chunk.page_number != int(value):
            return False
        if key == "has_table":
            has_table = chunk.chunk_type == "table" or bool(chunk.metadata.get("has_table"))
            if bool(value) != has_table:
                return False
        if key not in {"parser_name", "chunk_type", "page_number", "has_table"}:
            if chunk.metadata.get(key) != value:
                return False
    return True

from __future__ import annotations

from src.chunkers.base import ChunkerConfig, ChunkingRequest
from src.chunkers.fixed_size_chunker import FixedSizeChunker
from src.retrieval.embeddings import (
    EmbeddingConfig,
    EmbeddingProvider,
    EmbeddingRequest,
    HashingEmbeddingProvider,
)
from src.retrieval.index import (
    EmbeddingInMemoryIndex,
    LexicalInMemoryIndex,
    SearchRequest,
)
from src.schemas import ParsedDocument, ParsedPage, TableBlock, TextBlock


def test_fixed_size_chunker_uses_text_and_table_blocks() -> None:
    document = ParsedDocument(
        document_id="doc",
        source_path="/tmp/doc.pdf",
        parser_name="mineru",
        pages=[
            ParsedPage(
                page_number=1,
                text_blocks=[
                    TextBlock(
                        block_id="text-1",
                        page_number=1,
                        text="청년수당 주요 일정과 지급일 안내",
                    )
                ],
                table_blocks=[
                    TableBlock(
                        table_id="table-1",
                        page_number=1,
                        parser_name="mineru",
                        markdown="| 회차 | 지급일 |\n| --- | --- |\n| 1회 | 4월 30일 |",
                    )
                ],
            )
        ],
    )

    chunks = FixedSizeChunker().chunk(
        ChunkingRequest(
            document=document,
            config=ChunkerConfig(
                chunker_name="fixed_size",
                target_chunk_size=80,
                overlap=10,
            ),
        )
    )

    assert [chunk.chunk_type for chunk in chunks] == ["text", "table"]
    assert chunks[0].parser_name == "mineru"
    assert chunks[1].metadata["has_table"] is True


def test_fixed_size_chunker_falls_back_to_raw_table_cells() -> None:
    document = ParsedDocument(
        document_id="doc",
        source_path="/tmp/doc.pdf",
        parser_name="pdfplumber",
        pages=[
            ParsedPage(
                page_number=2,
                table_blocks=[
                    TableBlock(
                        table_id="table-raw",
                        page_number=2,
                        parser_name="pdfplumber",
                        raw_cells=[
                            ["항목", "금액"],
                            ["교통비", "50,000원"],
                        ],
                    )
                ],
            )
        ],
    )

    chunks = FixedSizeChunker().chunk(
        ChunkingRequest(
            document=document,
            config=ChunkerConfig(chunker_name="fixed_size"),
        )
    )

    assert len(chunks) == 1
    assert chunks[0].chunk_type == "table"
    assert "교통비 | 50,000원" in chunks[0].text


def test_fixed_size_chunker_coalesces_fragmented_text_blocks_by_page() -> None:
    document = ParsedDocument(
        document_id="doc",
        source_path="/tmp/doc.pdf",
        parser_name="opendataloader",
        pages=[
            ParsedPage(
                page_number=1,
                text_blocks=[
                    TextBlock(
                        block_id="text-1",
                        page_number=1,
                        text="자기성장기록서",
                    ),
                    TextBlock(
                        block_id="text-2",
                        page_number=1,
                        text="10일까지 작성 필수",
                    ),
                ],
            )
        ],
    )

    chunks = FixedSizeChunker().chunk(
        ChunkingRequest(
            document=document,
            config=ChunkerConfig(chunker_name="fixed_size"),
        )
    )

    assert len(chunks) == 1
    assert chunks[0].chunk_type == "page_text"
    assert chunks[0].source_block_ids == ["text-1", "text-2"]
    assert "자기성장기록서 10일까지 작성 필수" in chunks[0].text


def test_fixed_size_chunker_can_prepend_calendar_month_context_to_tables() -> None:
    document = ParsedDocument(
        document_id="doc",
        source_path="/tmp/doc.pdf",
        parser_name="mineru",
        pages=[
            ParsedPage(
                page_number=2,
                text_blocks=[
                    TextBlock(block_id="text-1", page_number=2, text="4월"),
                    TextBlock(block_id="text-2", page_number=2, text="5월"),
                    TextBlock(block_id="text-3", page_number=2, text="6월"),
                ],
                table_blocks=[
                    TableBlock(
                        table_id="table-1",
                        page_number=2,
                        parser_name="mineru",
                        markdown="| 29 지급② |",
                    ),
                    TableBlock(
                        table_id="table-2",
                        page_number=2,
                        parser_name="mineru",
                        markdown="| 29 지급③ |",
                    ),
                ],
            )
        ],
    )

    chunks = FixedSizeChunker().chunk(
        ChunkingRequest(
            document=document,
            config=ChunkerConfig(
                chunker_name="fixed_size",
                extra_options={
                    "prepend_page_text_to_tables": True,
                    "table_context_strategy": "calendar_month",
                },
            ),
        )
    )

    assert [chunk.chunk_id for chunk in chunks] == [
        "doc:mineru:p2:page_text:1",
        "doc:mineru:p2:table:2",
        "doc:mineru:p2:table:3",
    ]
    assert chunks[1].text.startswith("4월 ")
    assert chunks[1].metadata["context_title"] == "4월"
    assert chunks[2].text.startswith("6월 ")
    assert chunks[2].metadata["context_title"] == "6월"


def test_lexical_in_memory_index_searches_and_filters() -> None:
    document = ParsedDocument(
        document_id="doc",
        source_path="/tmp/doc.pdf",
        parser_name="mineru",
        pages=[
            ParsedPage(
                page_number=8,
                table_blocks=[
                    TableBlock(
                        table_id="table-1",
                        page_number=8,
                        parser_name="mineru",
                        markdown="| 회차 | 지급일 |\n| --- | --- |\n| 1회 | 4월 30일 |",
                    )
                ],
            )
        ],
    )
    chunks = FixedSizeChunker().chunk(
        ChunkingRequest(
            document=document,
            config=ChunkerConfig(chunker_name="fixed_size"),
        )
    )
    index = LexicalInMemoryIndex()
    index.build(chunks)

    results = index.search(
        SearchRequest(
            query_id="q1",
            query_text="지급일",
            top_k=3,
            filters={"chunk_type": "table", "page_number": 8},
        )
    )

    assert len(results) == 1
    assert results[0].rank == 1
    assert results[0].metadata["chunk_type"] == "table"
    assert "지급일" in str(results[0].metadata["text_preview"])


def test_embedding_in_memory_index_searches_with_provider_vectors() -> None:
    document = ParsedDocument(
        document_id="doc",
        source_path="/tmp/doc.pdf",
        parser_name="mineru",
        pages=[
            ParsedPage(
                page_number=1,
                text_blocks=[
                    TextBlock(
                        block_id="text-1",
                        page_number=1,
                        text="청년수당 신청 자격 안내",
                    )
                ],
                table_blocks=[
                    TableBlock(
                        table_id="table-1",
                        page_number=1,
                        parser_name="mineru",
                        markdown="| 회차 | 지급일 |\n| --- | --- |\n| 1회 | 4월 30일 |",
                    )
                ],
            )
        ],
    )
    chunks = FixedSizeChunker().chunk(
        ChunkingRequest(
            document=document,
            config=ChunkerConfig(chunker_name="fixed_size"),
        )
    )
    index = EmbeddingInMemoryIndex(_KeywordEmbeddingProvider())
    index.build(chunks)

    results = index.search(
        SearchRequest(
            query_id="q1",
            query_text="지급일",
            top_k=2,
            filters={"chunk_type": "table"},
        )
    )

    assert len(results) == 1
    assert results[0].chunk_id == "doc:mineru:p1:table:2"
    assert results[0].score == 1.0
    assert results[0].metadata["index_backend"] == "embedding_in_memory"


def test_hashing_embedding_provider_returns_fixed_size_vectors() -> None:
    provider = HashingEmbeddingProvider(
        EmbeddingConfig(
            provider_name="hashing",
            model_name="hashing-token-v1",
            extra_options={"dimensions": 8},
        )
    )

    vectors = provider.embed(
        EmbeddingRequest(texts=["지급일 안내", "자격 안내"], input_type="document")
    )

    assert len(vectors) == 2
    assert {len(vector) for vector in vectors} == {8}
    assert vectors[0] != vectors[1]


class _KeywordEmbeddingProvider(EmbeddingProvider):
    def embed(self, request: EmbeddingRequest) -> list[list[float]]:
        return [_embed_text(text) for text in request.texts]


def _embed_text(text: str) -> list[float]:
    return [
        1.0 if "지급" in text or "지급일" in text else 0.0,
        1.0 if "자격" in text else 0.0,
    ]

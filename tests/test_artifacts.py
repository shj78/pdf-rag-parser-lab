from __future__ import annotations

from src.artifacts import load_parsed_document, write_parsed_document
from src.schemas import BoundingBox, ParsedDocument, ParsedPage, TableBlock, TextBlock


def test_parsed_document_round_trip(tmp_path) -> None:
    document = ParsedDocument(
        document_id="sample-doc",
        source_path="/tmp/sample.pdf",
        parser_name="pdfplumber",
        pages=[
            ParsedPage(
                page_number=1,
                page_text="Heading\nValue",
                text_blocks=[
                    TextBlock(
                        block_id="sample-doc:p1:text:1",
                        page_number=1,
                        text="Heading",
                        bbox=BoundingBox(x0=1.0, y0=2.0, x1=3.0, y1=4.0),
                        metadata={"source": "unit-test"},
                    )
                ],
                table_blocks=[
                    TableBlock(
                        table_id="sample-doc:p1:table:1",
                        page_number=1,
                        parser_name="pdfplumber",
                        row_count=2,
                        col_count=2,
                        markdown="| A | B |\n| --- | --- |\n| 1 | 2 |",
                        raw_cells=[["A", "B"], ["1", "2"]],
                        metadata={"source": "unit-test"},
                    )
                ],
                metadata={"width": 100.0},
            )
        ],
        metadata={"is_baseline": True},
        warnings=["table bbox unavailable"],
    )

    artifact_path = tmp_path / "parsed_document.json"
    write_parsed_document(artifact_path, document)
    loaded = load_parsed_document(artifact_path)

    assert loaded == document

from __future__ import annotations

import json

import yaml

from experiments.parser_comparison.run_experiment import run_parser_comparison_from_file
from src.parsers.base import BasePDFParser
from src.parsers.schemas import ParseRequest, ParserDescriptor
from src.schemas import ParsedDocument, ParsedPage, TableBlock, TextBlock


class FakeBaselineParser(BasePDFParser):
    name = "pdfplumber"
    is_baseline = True

    @classmethod
    def describe(cls) -> ParserDescriptor:
        return ParserDescriptor(
            name=cls.name,
            display_name="Fake Baseline",
            description="fake baseline",
            is_baseline=True,
        )

    def parse(self, request: ParseRequest) -> ParsedDocument:
        return ParsedDocument(
            document_id=request.document_id,
            source_path=str(request.source_path),
            parser_name=self.name,
            pages=[
                ParsedPage(
                    page_number=1,
                    page_text="baseline text",
                    text_blocks=[
                        TextBlock(
                            block_id=f"{request.document_id}:p1:text:1",
                            page_number=1,
                            text="baseline text",
                        )
                    ],
                    table_blocks=[
                        TableBlock(
                            table_id=f"{request.document_id}:p1:table:1",
                            page_number=1,
                            parser_name=self.name,
                            row_count=2,
                            col_count=2,
                            raw_cells=[["A", "B"], ["1", "2"]],
                            markdown="| A | B |\n| --- | --- |\n| 1 | 2 |",
                        )
                    ],
                )
            ],
        )


class FakeCandidateParser(BasePDFParser):
    name = "pymupdf"

    @classmethod
    def describe(cls) -> ParserDescriptor:
        return ParserDescriptor(
            name=cls.name,
            display_name="Fake Candidate",
            description="fake candidate",
        )

    def parse(self, request: ParseRequest) -> ParsedDocument:
        return ParsedDocument(
            document_id=request.document_id,
            source_path=str(request.source_path),
            parser_name=self.name,
            pages=[
                ParsedPage(
                    page_number=1,
                    page_text="candidate text",
                    text_blocks=[
                        TextBlock(
                            block_id=f"{request.document_id}:p1:text:1",
                            page_number=1,
                            text="candidate text",
                        ),
                        TextBlock(
                            block_id=f"{request.document_id}:p1:text:2",
                            page_number=1,
                            text="extra block",
                        ),
                    ],
                )
            ],
            warnings=["candidate warning"],
        )


class BrokenParser(BasePDFParser):
    name = "opendataloader"

    @classmethod
    def describe(cls) -> ParserDescriptor:
        return ParserDescriptor(
            name=cls.name,
            display_name="Broken Parser",
            description="broken parser",
        )

    def parse(self, request: ParseRequest) -> ParsedDocument:
        raise NotImplementedError("not wired yet")


def test_parser_comparison_runner_writes_artifacts(tmp_path, monkeypatch) -> None:
    from src.parsers import factory

    monkeypatch.setattr(
        factory,
        "PARSER_REGISTRY",
        {
            "pdfplumber": FakeBaselineParser,
            "pymupdf": FakeCandidateParser,
            "opendataloader": BrokenParser,
        },
    )

    document_dir = tmp_path / "pdfs"
    document_dir.mkdir()
    (document_dir / "sample.pdf").write_bytes(b"%PDF-1.4\n")

    config_path = tmp_path / "parser-config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "experiment": {
                    "name": "parser_comparison",
                    "run_name": "unit-test-run",
                },
                "inputs": {
                    "document_dir": "./pdfs",
                    "file_glob": "*.pdf",
                },
                "parsers": {
                    "baseline": "pdfplumber",
                    "candidates": ["pdfplumber", "pymupdf", "opendataloader"],
                },
                "comparison": {
                    "include_text_blocks": True,
                    "include_tables": True,
                    "save_parsed_documents": True,
                },
                "output": {
                    "run_dir": "./runs/unit-test-run",
                },
            }
        ),
        encoding="utf-8",
    )

    summary = run_parser_comparison_from_file(config_path)
    run_dir = tmp_path / "runs" / "unit-test-run"

    assert summary["document_count"] == 1
    assert summary["per_parser"]["pdfplumber"]["success_count"] == 1
    assert summary["per_parser"]["pymupdf"]["success_count"] == 1
    assert summary["per_parser"]["opendataloader"]["failure_count"] == 1
    assert (run_dir / "parsed_documents" / "pdfplumber" / "sample.json").exists()
    assert (run_dir / "parsed_documents" / "pymupdf" / "sample.json").exists()
    assert (run_dir / "comparisons" / "sample.json").exists()

    comparison_payload = json.loads(
        (run_dir / "comparisons" / "sample.json").read_text(encoding="utf-8")
    )
    assert comparison_payload["parsers"]["pdfplumber"]["status"] == "success"
    assert (
        comparison_payload["parsers"]["pymupdf"]["comparison_to_baseline"]["status"]
        == "compared"
    )
    assert comparison_payload["parsers"]["opendataloader"]["status"] == "error"

"""Unit tests for the MinerU parser adapter.

실제 mineru CLI 실행은 별도 venv (.venv-mineru) 가 필요하므로 여기서는 다루지
않는다. subprocess 를 거치지 않는 정규화 로직과 환경 검증만 테스트한다.
"""

from __future__ import annotations

import pytest

from src.parsers import factory
from src.parsers.mineru_parser import (
    MinerUParser,
    _MinerUTableHTMLParser,
    _parse_html_table_to_rows,
)
from src.parsers.schemas import ParserConfig


def test_describe_returns_expected_metadata() -> None:
    descriptor = MinerUParser.describe()
    assert descriptor.name == "mineru"
    assert descriptor.display_name == "MinerU 파서"
    assert any("OCR" in s for s in descriptor.strengths)


def test_factory_registers_mineru() -> None:
    parser = factory.create_parser("mineru")
    assert isinstance(parser, MinerUParser)
    assert parser.config.parser_name == "mineru"
    assert "mineru" in {desc.name for desc in factory.list_parser_descriptors()}


def test_validate_environment_raises_when_cli_missing(monkeypatch) -> None:
    monkeypatch.setattr("src.parsers.mineru_parser.shutil.which", lambda _: None)
    with pytest.raises(RuntimeError, match="mineru.*not found"):
        MinerUParser().validate_environment()


def test_html_table_parser_extracts_rows() -> None:
    html = (
        "<html><body><table>"
        "<tr><th>회차</th><th>기간</th></tr>"
        "<tr><td>1회</td><td>상반기</td></tr>"
        "<tr><td>2회</td><td>하반기</td></tr>"
        "</table></body></html>"
    )
    parser = _MinerUTableHTMLParser()
    parser.feed(html)
    parser.close()
    assert parser.rows == [
        ["회차", "기간"],
        ["1회", "상반기"],
        ["2회", "하반기"],
    ]


def test_parse_html_table_to_rows_returns_empty_on_blank() -> None:
    warnings: list[str] = []
    assert _parse_html_table_to_rows("", warnings, 1, 1) == []
    assert warnings == []


def test_build_pages_normalizes_content_list() -> None:
    parser = MinerUParser(
        ParserConfig(parser_name="mineru", parse_tables=True)
    )
    content_items = [
        {"type": "title", "text": "안내책자", "text_level": 1, "page_idx": 0},
        {"type": "text", "text": "본 안내는...", "page_idx": 0},
        {"type": "text", "text": "  ", "page_idx": 0},  # 빈 텍스트 → 무시
        {
            "type": "table",
            "page_idx": 1,
            "table_body": (
                "<html><body><table>"
                "<tr><td>회차</td><td>기간</td></tr>"
                "<tr><td>1회</td><td>상반기</td></tr>"
                "</table></body></html>"
            ),
            "table_caption": ["일정표"],
            "table_footnote": [],
        },
    ]
    warnings: list[str] = []
    pages = parser._build_pages(
        document_id="doc1",
        content_items=content_items,
        parse_tables=True,
        warnings=warnings,
    )

    assert len(pages) == 2

    page1 = pages[0]
    assert page1.page_number == 1
    assert len(page1.text_blocks) == 2
    assert page1.text_blocks[0].text == "안내책자"
    assert page1.text_blocks[0].block_type == "title"
    assert page1.text_blocks[0].block_id == "doc1:p1:text:1"
    assert page1.table_blocks == []
    assert "안내책자" in page1.page_text

    page2 = pages[1]
    assert page2.page_number == 2
    assert page2.text_blocks == []
    assert len(page2.table_blocks) == 1
    table = page2.table_blocks[0]
    assert table.table_id == "doc1:p2:table:1"
    assert table.parser_name == "mineru"
    assert table.raw_cells == [["회차", "기간"], ["1회", "상반기"]]
    assert table.row_count == 2
    assert table.col_count == 2
    assert table.markdown is not None
    assert "회차" in table.markdown
    assert table.caption == "일정표"
    assert warnings == []


def test_build_pages_skips_tables_when_disabled() -> None:
    parser = MinerUParser()
    content_items = [
        {
            "type": "table",
            "page_idx": 0,
            "table_body": "<table><tr><td>x</td></tr></table>",
        },
    ]
    pages = parser._build_pages(
        document_id="doc1",
        content_items=content_items,
        parse_tables=False,
        warnings=[],
    )
    assert pages[0].table_blocks == []


def test_build_command_includes_page_range() -> None:
    from pathlib import Path

    cmd = MinerUParser._build_command(
        pdf_path=Path("/tmp/x.pdf"),
        output_dir=Path("/tmp/out"),
        backend="pipeline",
        language="korean",
        method=None,
        page_range=(0, 2),
    )
    assert cmd[:7] == ["mineru", "-p", "/tmp/x.pdf", "-o", "/tmp/out", "-b", "pipeline"]
    assert "-l" in cmd and "korean" in cmd
    assert cmd[-4:] == ["-s", "0", "-e", "2"]


def test_build_command_omits_page_range_when_none() -> None:
    from pathlib import Path

    cmd = MinerUParser._build_command(
        pdf_path=Path("/tmp/x.pdf"),
        output_dir=Path("/tmp/out"),
        backend="pipeline",
        language="korean",
        method=None,
        page_range=None,
    )
    assert "-s" not in cmd
    assert "-e" not in cmd


def test_build_command_includes_method_when_provided() -> None:
    from pathlib import Path

    cmd = MinerUParser._build_command(
        pdf_path=Path("/tmp/x.pdf"),
        output_dir=Path("/tmp/out"),
        backend="pipeline",
        language="korean",
        method="ocr",
        page_range=None,
    )
    assert "-m" in cmd
    assert cmd[cmd.index("-m") + 1] == "ocr"

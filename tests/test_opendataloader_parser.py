"""Unit tests for the OpenDataLoader parser adapter.

실제 CLI 실행과 hybrid 백엔드 시동은 별도 venv (.venv-opendataloader) 와
포트 5002 서버가 필요하므로 여기서는 다루지 않는다. subprocess 를 거치지 않는
정규화 로직과 환경 검증만 테스트한다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.parsers import factory
from src.parsers.opendataloader_parser import (
    DEFAULT_CLI_PATH,
    DEFAULT_HYBRID_URL,
    OpenDataLoaderParser,
    _iter_content_nodes,
)
from src.parsers.schemas import ParserConfig


def test_describe_returns_expected_metadata() -> None:
    descriptor = OpenDataLoaderParser.describe()
    assert descriptor.name == "opendataloader"
    assert descriptor.display_name == "OpenDataLoader-PDF"
    assert any("hybrid" in s.lower() for s in descriptor.strengths)
    assert any("local" in lim.lower() for lim in descriptor.known_limitations)


def test_factory_registers_opendataloader() -> None:
    parser = factory.create_parser("opendataloader")
    assert isinstance(parser, OpenDataLoaderParser)
    assert parser.config.parser_name == "opendataloader"
    names = {desc.name for desc in factory.list_parser_descriptors()}
    assert "opendataloader" in names


def test_validate_environment_raises_when_cli_missing(tmp_path: Path) -> None:
    missing = tmp_path / "nope" / "opendataloader-pdf"
    parser = OpenDataLoaderParser(
        ParserConfig(parser_name="opendataloader", extra_options={"cli_path": missing})
    )
    with pytest.raises(RuntimeError, match="opendataloader-pdf CLI not found"):
        parser.validate_environment()


def test_validate_environment_hybrid_raises_when_server_unreachable(
    tmp_path: Path,
) -> None:
    fake_cli = tmp_path / "opendataloader-pdf"
    fake_cli.write_text("#!/bin/sh\nexit 0\n")
    parser = OpenDataLoaderParser(
        ParserConfig(
            parser_name="opendataloader",
            extra_options={
                "cli_path": fake_cli,
                "hybrid_backend": "docling-fast",
                "hybrid_url": "http://127.0.0.1:1",
            },
        )
    )
    with pytest.raises(RuntimeError, match="hybrid backend.*unreachable"):
        parser.validate_environment()


def test_build_command_local_mode_omits_hybrid_flags() -> None:
    cmd = OpenDataLoaderParser._build_command(
        cli_path=Path("/usr/bin/opendataloader-pdf"),
        pdf_path=Path("/tmp/x.pdf"),
        output_dir=Path("/tmp/out"),
        hybrid_backend="off",
        hybrid_url=DEFAULT_HYBRID_URL,
        hybrid_mode="auto",
        pages=None,
    )
    assert cmd[0] == "/usr/bin/opendataloader-pdf"
    assert cmd[-1] == "/tmp/x.pdf"  # positional input must be last
    assert "--hybrid" not in cmd
    assert "--hybrid-url" not in cmd
    assert "--pages" not in cmd
    assert "--input-path" not in cmd  # CLI takes positional, not flagged
    assert "--output-dir" in cmd and "/tmp/out" in cmd
    assert "--format" in cmd and "json" in cmd


def test_build_command_hybrid_mode_includes_backend_and_pages() -> None:
    cmd = OpenDataLoaderParser._build_command(
        cli_path=Path(DEFAULT_CLI_PATH),
        pdf_path=Path("/tmp/x.pdf"),
        output_dir=Path("/tmp/out"),
        hybrid_backend="docling-fast",
        hybrid_url="http://localhost:5002",
        hybrid_mode="full",
        pages="1-3",
    )
    assert cmd[-1] == "/tmp/x.pdf"
    assert "--hybrid" in cmd
    assert cmd[cmd.index("--hybrid") + 1] == "docling-fast"
    assert "--hybrid-url" in cmd
    assert cmd[cmd.index("--hybrid-url") + 1] == "http://localhost:5002"
    assert "--hybrid-mode" in cmd
    assert cmd[cmd.index("--hybrid-mode") + 1] == "full"
    assert "--pages" in cmd
    assert cmd[cmd.index("--pages") + 1] == "1-3"


def test_build_command_includes_table_method_when_configured() -> None:
    cmd = OpenDataLoaderParser._build_command(
        cli_path=Path(DEFAULT_CLI_PATH),
        pdf_path=Path("/tmp/x.pdf"),
        output_dir=Path("/tmp/out"),
        hybrid_backend="off",
        hybrid_url=DEFAULT_HYBRID_URL,
        hybrid_mode="auto",
        table_method="cluster",
        pages=None,
    )

    assert cmd[-1] == "/tmp/x.pdf"
    assert "--table-method" in cmd
    assert cmd[cmd.index("--table-method") + 1] == "cluster"


def test_build_command_includes_hancom_ai_options_when_configured() -> None:
    cmd = OpenDataLoaderParser._build_command(
        cli_path=Path(DEFAULT_CLI_PATH),
        pdf_path=Path("/tmp/x.pdf"),
        output_dir=Path("/tmp/out"),
        hybrid_backend="hancom-ai",
        hybrid_url="http://localhost:5002",
        hybrid_mode="full",
        table_method="cluster",
        pages="1",
        hybrid_timeout="120000",
        hybrid_fallback=True,
        hancom_regionlist_strategy="table-first",
        hancom_ocr_strategy="force",
        hancom_image_cache="disk",
    )

    assert cmd[cmd.index("--hybrid") + 1] == "hancom-ai"
    assert cmd[cmd.index("--table-method") + 1] == "cluster"
    assert cmd[cmd.index("--hybrid-timeout") + 1] == "120000"
    assert "--hybrid-fallback" in cmd
    assert (
        cmd[cmd.index("--hybrid-hancom-ai-regionlist-strategy") + 1]
        == "table-first"
    )
    assert cmd[cmd.index("--hybrid-hancom-ai-ocr-strategy") + 1] == "force"
    assert cmd[cmd.index("--hybrid-hancom-ai-image-cache") + 1] == "disk"
    assert cmd[-1] == "/tmp/x.pdf"


def test_iter_content_nodes_skips_synthetic_root() -> None:
    root = {
        "file name": "x.pdf",
        "kids": [
            {"type": "paragraph", "content": "hi", "page number": 1, "kids": []},
            {
                "type": "section",
                "kids": [
                    {"type": "heading", "content": "h", "page number": 2, "kids": []},
                ],
            },
        ],
    }
    nodes = list(_iter_content_nodes(root))
    types = [n.get("type") for n in nodes]
    assert types == ["paragraph", "section", "heading"]


def test_build_pages_normalizes_paragraphs_and_headings() -> None:
    parser = OpenDataLoaderParser()
    root = {
        "file name": "안내책자.pdf",
        "kids": [
            {
                "type": "heading",
                "content": "안내책자",
                "heading level": 1,
                "page number": 1,
                "id": "h1",
                "bounding box": [10, 20, 110, 50],
            },
            {
                "type": "paragraph",
                "content": "본 안내는 ...",
                "page number": 1,
                "id": "p1",
            },
            {
                "type": "paragraph",
                "content": "  ",
                "page number": 1,
                "id": "p_blank",
            },
            {
                "type": "paragraph",
                "content": "두번째 페이지 본문",
                "page number": 2,
                "id": "p2",
            },
            {
                "type": "image",
                "content": "",
                "page number": 2,
                "id": "img1",
            },
        ],
    }
    warnings: list[str] = []
    pages = parser._build_pages(
        document_id="doc1",
        root=root,
        warnings=warnings,
    )

    assert [p.page_number for p in pages] == [1, 2]

    page1 = pages[0]
    assert len(page1.text_blocks) == 2
    heading_block, para_block = page1.text_blocks
    assert heading_block.text == "안내책자"
    assert heading_block.block_type == "heading"
    assert heading_block.block_id == "doc1:p1:text:1"
    assert heading_block.bbox is not None
    assert heading_block.bbox.x0 == 10.0
    assert heading_block.bbox.x1 == 110.0
    assert heading_block.metadata["heading_level"] == 1
    assert para_block.text == "본 안내는 ..."
    assert para_block.block_type == "text"
    assert "안내책자" in page1.page_text

    page2 = pages[1]
    assert len(page2.text_blocks) == 1
    assert page2.text_blocks[0].text == "두번째 페이지 본문"
    assert page2.table_blocks == []
    assert warnings == []


def test_build_pages_warns_on_missing_page_number() -> None:
    parser = OpenDataLoaderParser()
    root = {
        "kids": [
            {"type": "paragraph", "content": "no page", "id": "p1"},
            {"type": "paragraph", "content": "ok", "page number": 1, "id": "p2"},
        ]
    }
    warnings: list[str] = []
    pages = parser._build_pages(document_id="d", root=root, warnings=warnings)
    assert len(pages) == 1
    assert pages[0].text_blocks[0].text == "ok"
    assert len(warnings) == 1
    assert "missing page number" in warnings[0]

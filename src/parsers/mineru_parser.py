"""MinerU parser adapter (CLI subprocess based).

실측 검증 기록: ``experiments/parser_candidates_verification.md`` §9-2.
CLI 호출 명령: ``mineru -p <pdf> -o <out> -b pipeline -l korean [-s S -e E]``.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
from collections import defaultdict
from html.parser import HTMLParser
from importlib import import_module
from pathlib import Path
from typing import Any

from src.schemas import ParsedDocument, ParsedPage, TableBlock, TextBlock

from .base import BasePDFParser
from .helpers import normalize_cell, table_rows_to_markdown
from .schemas import ParseRequest, ParserDescriptor

logger = logging.getLogger(__name__)


class MinerUParser(BasePDFParser):
    """MinerU 어댑터 — CLI 를 호출하고 content_list.json 을 정규화한다.

    extra_options 키:
    - backend: "pipeline" (CPU, 기본) / "vlm-transformers" 등
    - language: "korean" (기본)
    - page_range: (start, end) 0-indexed inclusive — 없으면 전체
    """

    name = "mineru"

    @classmethod
    def describe(cls) -> ParserDescriptor:
        return ParserDescriptor(
            name=cls.name,
            display_name="MinerU Parser",
            description=(
                "OCR 내장 PDF 파서. 한국어 안내책자형 PDF 의 표/이미지/달력 "
                "구조를 markdown + content_list.json 으로 추출한다."
            ),
            strengths=[
                "내장 OCR — 텍스트 레이어가 없는 PDF 도 처리",
                "표를 HTML <table> 로 보존, 헤딩 자동 부여",
                "단일 진입점 (별도 백엔드 서버 불필요)",
            ],
            known_limitations=[
                "첫 실행 시 약 1.1 GB 모델 자동 다운로드",
                "CPU pipeline 백엔드 기준 페이지당 약 30 초 (Apple Silicon)",
                "OCR 오인식 가능 (예: '1회차' → '1회찬')",
            ],
        )

    def validate_environment(self) -> None:
        if shutil.which("mineru") is None:
            raise RuntimeError(
                "`mineru` CLI not found on PATH. Install via `pipenv install` "
                "after adding `mineru[core]` to Pipfile."
            )
        import_module("mineru")

    def parse(self, request: ParseRequest) -> ParsedDocument:
        self.validate_environment()

        extra = request.config.extra_options or {}
        backend = str(extra.get("backend", "pipeline"))
        language = str(extra.get("language", "korean"))
        page_range = extra.get("page_range")

        warnings: list[str] = []

        with tempfile.TemporaryDirectory(prefix="mineru-") as tmpdir:
            output_dir = Path(tmpdir)
            cmd = self._build_command(
                pdf_path=request.source_path,
                output_dir=output_dir,
                backend=backend,
                language=language,
                page_range=page_range,
            )
            logger.info("Running MinerU: %s", " ".join(cmd))

            result = subprocess.run(
                cmd, capture_output=True, text=True, check=False
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"MinerU failed (exit {result.returncode}). "
                    f"stderr tail: {result.stderr[-500:]!r}"
                )

            content_list_path = self._find_content_list(output_dir)
            if content_list_path is None:
                raise RuntimeError(
                    f"MinerU finished but no *_content_list.json found under {output_dir}"
                )

            with content_list_path.open(encoding="utf-8") as fp:
                content_items = json.load(fp)

            pages = self._build_pages(
                document_id=request.document_id,
                content_items=content_items,
                parse_tables=request.config.parse_tables,
                warnings=warnings,
            )

        return ParsedDocument(
            document_id=request.document_id,
            source_path=str(request.source_path),
            parser_name=self.name,
            pages=pages,
            metadata={
                "backend": backend,
                "language": language,
                "page_range": list(page_range) if page_range else None,
            },
            warnings=warnings,
        )

    @staticmethod
    def _build_command(
        pdf_path: Path,
        output_dir: Path,
        backend: str,
        language: str,
        page_range: tuple[int, int] | list[int] | None,
    ) -> list[str]:
        cmd = [
            "mineru",
            "-p", str(pdf_path),
            "-o", str(output_dir),
            "-b", backend,
            "-l", language,
        ]
        if page_range is not None:
            start, end = int(page_range[0]), int(page_range[1])
            cmd.extend(["-s", str(start), "-e", str(end)])
        return cmd

    @staticmethod
    def _find_content_list(output_dir: Path) -> Path | None:
        candidates = sorted(output_dir.rglob("*_content_list.json"))
        return candidates[0] if candidates else None

    def _build_pages(
        self,
        document_id: str,
        content_items: list[dict[str, Any]],
        parse_tables: bool,
        warnings: list[str],
    ) -> list[ParsedPage]:
        by_page: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for item in content_items:
            page_idx = int(item.get("page_idx", 0))
            by_page[page_idx].append(item)

        pages: list[ParsedPage] = []
        for page_idx in sorted(by_page):
            page_number = page_idx + 1
            text_blocks: list[TextBlock] = []
            table_blocks: list[TableBlock] = []
            page_text_parts: list[str] = []

            for item in by_page[page_idx]:
                item_type = str(item.get("type", ""))

                if item_type in ("text", "title", "equation"):
                    text = str(item.get("text") or "").strip()
                    if not text:
                        continue
                    page_text_parts.append(text)
                    text_blocks.append(
                        TextBlock(
                            block_id=(
                                f"{document_id}:p{page_number}:text:{len(text_blocks) + 1}"
                            ),
                            page_number=page_number,
                            text=text,
                            block_type=item_type,
                            metadata={
                                "source": "mineru.content_list",
                                "text_level": item.get("text_level"),
                                "text_format": item.get("text_format"),
                            },
                        )
                    )
                elif item_type == "table":
                    if not parse_tables:
                        continue
                    table_index = len(table_blocks) + 1
                    table_html = str(item.get("table_body") or "")
                    raw_cells = _parse_html_table_to_rows(
                        table_html, warnings, page_number, table_index
                    )
                    caption_list = item.get("table_caption") or []
                    caption = (
                        " ".join(str(c) for c in caption_list).strip() or None
                        if caption_list
                        else None
                    )
                    table_blocks.append(
                        TableBlock(
                            table_id=(
                                f"{document_id}:p{page_number}:table:{table_index}"
                            ),
                            page_number=page_number,
                            parser_name=self.name,
                            row_count=len(raw_cells) or None,
                            col_count=max(
                                (len(row) for row in raw_cells), default=0
                            ) or None,
                            markdown=table_rows_to_markdown(raw_cells),
                            raw_cells=raw_cells,
                            caption=caption,
                            metadata={
                                "source": "mineru.content_list",
                                "table_body_html": table_html,
                                "table_footnote": item.get("table_footnote"),
                            },
                        )
                    )

            pages.append(
                ParsedPage(
                    page_number=page_number,
                    page_text="\n".join(page_text_parts).strip(),
                    text_blocks=text_blocks,
                    table_blocks=table_blocks,
                    metadata={},
                )
            )

        return pages


class _MinerUTableHTMLParser(HTMLParser):
    """MinerU 의 table_body HTML 을 행렬 리스트로 분해한다.

    rowspan/colspan 은 이번 라운드에서 직접 펼치지 않고 단일 셀로 기록한다.
    """

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._current_row: list[str] | None = None
        self._cell_text: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._current_row = []
        elif tag in ("td", "th") and self._current_row is not None:
            self._cell_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "tr" and self._current_row is not None:
            if self._current_row:
                self.rows.append(self._current_row)
            self._current_row = None
        elif (
            tag in ("td", "th")
            and self._current_row is not None
            and self._cell_text is not None
        ):
            self._current_row.append(normalize_cell("".join(self._cell_text)))
            self._cell_text = None

    def handle_data(self, data: str) -> None:
        if self._cell_text is not None:
            self._cell_text.append(data)


def _parse_html_table_to_rows(
    html: str,
    warnings: list[str],
    page_number: int,
    table_index: int,
) -> list[list[str]]:
    if not html.strip():
        return []
    parser = _MinerUTableHTMLParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception as exc:  # pragma: no cover - defensive
        warnings.append(
            f"page {page_number}: table {table_index} HTML parse failed ({exc})"
        )
        return []
    return parser.rows


__all__ = ["MinerUParser"]

"""OpenDataLoader-PDF parser adapter (CLI subprocess based).

실측 검증 기록: ``experiments/parser_candidates_verification.md`` §9-1, §9-3.

격리 venv (``.venv-opendataloader/``) 의 ``opendataloader-pdf`` CLI 를 호출한다.
hybrid 모드는 별도 백엔드 서버 (`opendataloader-pdf-hybrid --port 5002`) 가
사전 시동돼 있어야 한다 (어댑터는 health check 만 수행, lifecycle 관리는 외부).
"""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any

from src.schemas import ParsedDocument, ParsedPage, TextBlock

from .base import BasePDFParser
from .helpers import build_bbox
from .schemas import ParserDescriptor, ParseRequest

logger = logging.getLogger(__name__)

DEFAULT_CLI_PATH = Path(".venv-opendataloader/bin/opendataloader-pdf")
DEFAULT_HYBRID_URL = "http://127.0.0.1:5002"


class OpenDataLoaderParser(BasePDFParser):
    """OpenDataLoader 어댑터 — CLI 를 호출하고 JSON 출력을 정규화한다.

    extra_options 키:
    - cli_path: CLI 실행 파일 경로 (기본: .venv-opendataloader/bin/opendataloader-pdf)
    - hybrid_backend: "off" (기본, local 모드) / "docling-fast" / "hancom-ai"
    - hybrid_url: hybrid 백엔드 URL (기본: http://127.0.0.1:5002)
    - hybrid_mode: "auto" (기본) / "full"
    - table_method: "default" / "cluster" (없으면 CLI 기본값)
    - pages: "1-3" 형식 (없으면 전체)
    - hybrid_timeout: hybrid 요청 timeout milliseconds
    - hybrid_fallback: true 면 hybrid 실패 시 Java fallback 허용
    - hybrid_hancom_ai_regionlist_strategy: "table-first" / "list-only"
    - hybrid_hancom_ai_ocr_strategy: "off" / "auto" / "force"
    - hybrid_hancom_ai_image_cache: "memory" / "disk"
    """

    name = "opendataloader"

    @classmethod
    def describe(cls) -> ParserDescriptor:
        return ParserDescriptor(
            name=cls.name,
            display_name="OpenDataLoader-PDF",
            description=(
                "Hancom AI OpenDataLoader-PDF. Java 기반 local 추출 + 선택적 "
                "hybrid (docling-fast / hancom-ai) 백엔드 OCR."
            ),
            strengths=[
                "Java + Python wrapper — 단일 패키지 설치",
                "Hybrid 모드에서 EasyOCR/Tesseract 등 다중 OCR 엔진 선택",
                "단순 텍스트 추출은 매우 빠름 (35페이지 4초대, §9-1)",
            ],
            known_limitations=[
                "Local 모드는 텍스트 레이어 없는 PDF (안내책자형) 에 빈 셀 출력 (§9-1)",
                "Hybrid 모드는 별도 백엔드 서버 (`opendataloader-pdf-hybrid`) 사전 시동 필요",
                "달력형 표가 각 셀별 paragraph 로 파편화 — HTML <table> 보존 안 됨 (§9-3)",
            ],
        )

    def validate_environment(self) -> None:
        extra = self.config.extra_options or {}
        cli = Path(str(extra.get("cli_path") or DEFAULT_CLI_PATH))
        if not cli.exists():
            raise RuntimeError(
                f"opendataloader-pdf CLI not found at {cli}. Create the isolated "
                "venv: `python -m venv .venv-opendataloader && "
                ".venv-opendataloader/bin/pip install 'opendataloader-pdf[hybrid]'` "
                "(see README §OpenDataLoader)."
            )

        backend = str(extra.get("hybrid_backend", "off"))
        if backend != "off":
            hybrid_url = str(extra.get("hybrid_url") or DEFAULT_HYBRID_URL)
            self._health_check_hybrid(hybrid_url)

    def parse(self, request: ParseRequest) -> ParsedDocument:
        self.validate_environment()

        extra = request.config.extra_options or {}
        cli = Path(str(extra.get("cli_path") or DEFAULT_CLI_PATH))
        backend = str(extra.get("hybrid_backend", "off"))
        hybrid_url = str(extra.get("hybrid_url") or DEFAULT_HYBRID_URL)
        hybrid_mode = str(extra.get("hybrid_mode", "auto"))
        table_method = extra.get("table_method")
        pages = extra.get("pages")
        hybrid_timeout = extra.get("hybrid_timeout")
        hybrid_fallback = bool(extra.get("hybrid_fallback", False))
        hancom_regionlist_strategy = extra.get(
            "hybrid_hancom_ai_regionlist_strategy"
        )
        hancom_ocr_strategy = extra.get("hybrid_hancom_ai_ocr_strategy")
        hancom_image_cache = extra.get("hybrid_hancom_ai_image_cache")

        warnings: list[str] = []

        with tempfile.TemporaryDirectory(prefix="odl-") as tmpdir:
            output_dir = Path(tmpdir)
            cmd = self._build_command(
                cli_path=cli,
                pdf_path=request.source_path,
                output_dir=output_dir,
                hybrid_backend=backend,
                hybrid_url=hybrid_url,
                hybrid_mode=hybrid_mode,
                table_method=str(table_method) if table_method is not None else None,
                pages=pages,
                hybrid_timeout=(
                    str(hybrid_timeout) if hybrid_timeout is not None else None
                ),
                hybrid_fallback=hybrid_fallback,
                hancom_regionlist_strategy=(
                    str(hancom_regionlist_strategy)
                    if hancom_regionlist_strategy is not None
                    else None
                ),
                hancom_ocr_strategy=(
                    str(hancom_ocr_strategy)
                    if hancom_ocr_strategy is not None
                    else None
                ),
                hancom_image_cache=(
                    str(hancom_image_cache) if hancom_image_cache is not None else None
                ),
            )
            logger.info("Running opendataloader-pdf: %s", " ".join(cmd))

            result = subprocess.run(
                cmd, capture_output=True, text=True, check=False
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"opendataloader-pdf failed (exit {result.returncode}). "
                    f"stderr tail: {result.stderr[-500:]!r}"
                )

            json_path = self._find_output_json(output_dir)
            if json_path is None:
                raise RuntimeError(
                    f"opendataloader-pdf finished but no *.json found under {output_dir}"
                )

            with json_path.open(encoding="utf-8") as fp:
                data = json.load(fp)

            parsed_pages = self._build_pages(
                document_id=request.document_id,
                root=data,
                warnings=warnings,
            )

        return ParsedDocument(
            document_id=request.document_id,
            source_path=str(request.source_path),
            parser_name=self.name,
            pages=parsed_pages,
            metadata={
                "hybrid_backend": backend,
                "hybrid_url": hybrid_url if backend != "off" else None,
                "hybrid_mode": hybrid_mode if backend != "off" else None,
                "table_method": str(table_method) if table_method is not None else None,
                "pages": pages,
                "hybrid_timeout": (
                    str(hybrid_timeout) if hybrid_timeout is not None else None
                ),
                "hybrid_fallback": hybrid_fallback if backend != "off" else None,
                "hybrid_hancom_ai_regionlist_strategy": (
                    str(hancom_regionlist_strategy)
                    if hancom_regionlist_strategy is not None
                    else None
                ),
                "hybrid_hancom_ai_ocr_strategy": (
                    str(hancom_ocr_strategy)
                    if hancom_ocr_strategy is not None
                    else None
                ),
                "hybrid_hancom_ai_image_cache": (
                    str(hancom_image_cache) if hancom_image_cache is not None else None
                ),
                "document_title": data.get("title"),
                "document_author": data.get("author"),
                "number_of_pages": data.get("number of pages"),
            },
            warnings=warnings,
        )

    @staticmethod
    def _build_command(
        cli_path: Path,
        pdf_path: Path,
        output_dir: Path,
        hybrid_backend: str,
        hybrid_url: str,
        hybrid_mode: str,
        table_method: str | None = None,
        pages: str | None = None,
        hybrid_timeout: str | None = None,
        hybrid_fallback: bool = False,
        hancom_regionlist_strategy: str | None = None,
        hancom_ocr_strategy: str | None = None,
        hancom_image_cache: str | None = None,
    ) -> list[str]:
        cmd: list[str] = [
            str(cli_path),
            "--output-dir", str(output_dir),
            "--format", "json",
        ]
        if table_method:
            cmd.extend(["--table-method", table_method])
        if hybrid_backend != "off":
            cmd.extend(["--hybrid", hybrid_backend])
            cmd.extend(["--hybrid-url", hybrid_url])
            cmd.extend(["--hybrid-mode", hybrid_mode])
            if hybrid_timeout:
                cmd.extend(["--hybrid-timeout", hybrid_timeout])
            if hybrid_fallback:
                cmd.append("--hybrid-fallback")
            if hancom_regionlist_strategy:
                cmd.extend(
                    [
                        "--hybrid-hancom-ai-regionlist-strategy",
                        hancom_regionlist_strategy,
                    ]
                )
            if hancom_ocr_strategy:
                cmd.extend(["--hybrid-hancom-ai-ocr-strategy", hancom_ocr_strategy])
            if hancom_image_cache:
                cmd.extend(["--hybrid-hancom-ai-image-cache", hancom_image_cache])
        if pages:
            cmd.extend(["--pages", str(pages)])
        cmd.append(str(pdf_path))
        return cmd

    @staticmethod
    def _find_output_json(output_dir: Path) -> Path | None:
        candidates = sorted(output_dir.rglob("*.json"))
        return candidates[0] if candidates else None

    @staticmethod
    def _health_check_hybrid(hybrid_url: str) -> None:
        probe_url = hybrid_url.rstrip("/") + "/docs"
        try:
            with urllib.request.urlopen(probe_url, timeout=3) as resp:
                if resp.status >= 400:
                    raise RuntimeError(
                        f"hybrid backend at {hybrid_url} responded {resp.status}"
                    )
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RuntimeError(
                f"hybrid backend at {hybrid_url} unreachable ({exc}). "
                "Start it with: `.venv-opendataloader/bin/opendataloader-pdf-hybrid "
                "--port 5002 --force-ocr --ocr-engine easyocr --ocr-lang ko,en`"
            ) from exc

    def _build_pages(
        self,
        document_id: str,
        root: dict[str, Any],
        warnings: list[str],
    ) -> list[ParsedPage]:
        nodes = list(_iter_content_nodes(root))

        by_page: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for node in nodes:
            page_number = _coerce_page_number(node)
            if page_number is None:
                warnings.append(
                    f"node id={node.get('id')!r} type={node.get('type')!r} "
                    "missing page number — skipped"
                )
                continue
            by_page[page_number].append(node)

        pages: list[ParsedPage] = []
        for page_number in sorted(by_page):
            text_blocks: list[TextBlock] = []
            page_text_parts: list[str] = []

            for node in by_page[page_number]:
                node_type = str(node.get("type", ""))
                content = str(node.get("content") or "").strip()
                if not content:
                    continue

                if node_type == "paragraph":
                    block_type = "text"
                elif node_type == "heading":
                    block_type = "heading"
                else:
                    continue

                page_text_parts.append(content)
                bbox_coords = _bbox_from_list(node.get("bounding box"))
                text_blocks.append(
                    TextBlock(
                        block_id=(
                            f"{document_id}:p{page_number}:text:{len(text_blocks) + 1}"
                        ),
                        page_number=page_number,
                        text=content,
                        bbox=build_bbox(*bbox_coords),
                        block_type=block_type,
                        metadata={
                            "source": "opendataloader.json",
                            "node_id": node.get("id"),
                            "font": node.get("font"),
                            "font_size": node.get("font size"),
                            "heading_level": node.get("heading level"),
                            "level": node.get("level"),
                        },
                    )
                )

            pages.append(
                ParsedPage(
                    page_number=page_number,
                    page_text="\n".join(page_text_parts).strip(),
                    text_blocks=text_blocks,
                    table_blocks=[],
                    metadata={},
                )
            )

        return pages


def _iter_content_nodes(node: dict[str, Any]) -> Any:
    """Depth-first traversal yielding every node (skipping the synthetic root)."""

    if node.get("type"):
        yield node
    for kid in node.get("kids") or []:
        yield from _iter_content_nodes(kid)


def _coerce_page_number(node: dict[str, Any]) -> int | None:
    raw = node.get("page number")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _bbox_from_list(
    raw: Any,
) -> tuple[float | None, float | None, float | None, float | None]:
    """OpenDataLoader uses ``[x0, y0, x1, y1]`` for bounding boxes."""

    if not isinstance(raw, list) or len(raw) < 4:
        return (None, None, None, None)
    try:
        return (float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3]))
    except (TypeError, ValueError):
        return (None, None, None, None)


__all__ = ["OpenDataLoaderParser"]

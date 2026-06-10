"""실행 가능한 파서 비교 페이지."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import streamlit as st

from experiments.parser_comparison.run_experiment import (
    ParserComparisonConfig,
    run_parser_comparison,
)
from src.parsers.factory import list_parser_descriptors

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DOCUMENT_DIR = PROJECT_ROOT / "assets"
DEFAULT_OUTPUT_BASE = PROJECT_ROOT / "artifacts" / "parser-lab-ui-runs"


def render_parser_comparison_page() -> None:
    """실행 가능한 파서 비교 화면을 렌더링한다."""

    st.subheader("파서 비교")

    descriptors = {descriptor.name: descriptor for descriptor in list_parser_descriptors()}
    parser_names = list(descriptors)

    with st.sidebar.expander("파서 실행", expanded=True):
        baseline_parser = st.selectbox(
            "기준 파서",
            options=parser_names,
            index=parser_names.index("pdfplumber") if "pdfplumber" in parser_names else 0,
        )
        selected_candidates = st.multiselect(
            "비교할 파서",
            options=parser_names,
            default=[name for name in ("pymupdf",) if name in parser_names],
            help="선택한 기준 파서는 실행 목록에 자동으로 포함됩니다.",
        )
        document_dir = Path(
            st.text_input("PDF 디렉터리", value=str(DEFAULT_DOCUMENT_DIR))
        ).expanduser()
        file_glob = st.text_input("파일 패턴", value="*.pdf")
        output_base = Path(
            st.text_input("결과 저장 위치", value=str(DEFAULT_OUTPUT_BASE))
        ).expanduser()
        parse_tables = st.checkbox("표 추출", value=True)
        preserve_layout = st.checkbox("레이아웃 보존", value=True)

    selected_parsers = _dedupe_preserving_order([baseline_parser, *selected_candidates])
    parser_options = _render_parser_options(selected_parsers)

    if not selected_parsers:
        st.warning("파서를 하나 이상 선택하세요.")
        return

    _render_parser_descriptors(descriptors, selected_parsers, baseline_parser)
    _render_run_guidance(selected_parsers, parser_options)
    _render_qa_notice()

    run_clicked = st.button("비교 실행", type="primary")
    if run_clicked:
        run_dir = output_base / _build_run_id()
        config = ParserComparisonConfig(
            config_path=PROJECT_ROOT / "apps" / "parser-lab-ui" / "app.py",
            run_name="streamlit-parser-comparison",
            document_dir=document_dir,
            file_glob=file_glob,
            baseline_parser=baseline_parser,
            candidate_parsers=selected_parsers,
            output_dir=run_dir,
            parse_tables=parse_tables,
            preserve_layout=preserve_layout,
            parser_options=parser_options,
        )
        with st.spinner("파서 비교를 실행하는 중입니다..."):
            try:
                summary = run_parser_comparison(config)
            except Exception as exc:
                st.error(f"{type(exc).__name__}: {exc}")
            else:
                st.session_state["parser_comparison_run_dir"] = str(run_dir)
                st.session_state["parser_comparison_summary"] = summary

    _render_latest_results()


def _render_parser_options(selected_parsers: list[str]) -> dict[str, dict[str, Any]]:
    options: dict[str, dict[str, Any]] = {}

    if "mineru" in selected_parsers:
        with st.sidebar.expander("MinerU 옵션"):
            if shutil.which("mineru") is None:
                st.warning(
                    "MinerU CLI가 현재 PATH에 없습니다. Streamlit을 다음처럼 다시 실행하세요: "
                    '`PATH=".venv-mineru/bin:$PATH" pipenv run streamlit run ...`.'
                )
            mineru_backend = st.text_input("MinerU 백엔드", value="pipeline")
            mineru_language = st.text_input("MinerU 언어", value="korean")
            mineru_page_range = st.text_input("MinerU 페이지 범위", value="")
            options["mineru"] = {
                "backend": mineru_backend,
                "language": mineru_language,
            }
            page_range = _parse_zero_based_page_range(mineru_page_range)
            if page_range is not None:
                options["mineru"]["page_range"] = page_range

    if "opendataloader" in selected_parsers:
        with st.sidebar.expander("OpenDataLoader 옵션"):
            cli_path = st.text_input(
                "OpenDataLoader CLI",
                value=str(PROJECT_ROOT / ".venv-opendataloader/bin/opendataloader-pdf"),
            )
            hybrid_backend = st.selectbox(
                "하이브리드 백엔드",
                options=["off", "docling-fast", "hancom-ai"],
            )
            if hybrid_backend == "off":
                st.warning(
                    "OCR이 필요한 PDF에서 local 모드는 추출 텍스트가 0개로 나올 수 있습니다. "
                    "OCR을 보려면 하이브리드 백엔드를 실행한 뒤 docling-fast를 선택하세요."
                )
            hybrid_url = st.text_input("하이브리드 URL", value="http://127.0.0.1:5002")
            hybrid_mode = st.selectbox("하이브리드 모드", options=["auto", "full"], index=0)
            pages = st.text_input("페이지", value="")
            options["opendataloader"] = {
                "cli_path": cli_path,
                "hybrid_backend": hybrid_backend,
            }
            if hybrid_backend != "off":
                options["opendataloader"]["hybrid_url"] = hybrid_url
                options["opendataloader"]["hybrid_mode"] = hybrid_mode
            if pages.strip():
                options["opendataloader"]["pages"] = pages.strip()

    return options


def _render_parser_descriptors(
    descriptors: dict[str, Any],
    selected_parsers: list[str],
    baseline_parser: str,
) -> None:
    cols = st.columns(min(len(selected_parsers), 4))
    for index, parser_name in enumerate(selected_parsers):
        descriptor = descriptors[parser_name]
        with cols[index % len(cols)]:
            st.metric(
                descriptor.display_name,
                "기준 파서" if parser_name == baseline_parser else "비교 대상",
            )
            with st.expander(f"{descriptor.display_name} 상세"):
                st.caption(f"기술 식별자: `{descriptor.name}`")
                st.write(descriptor.description)
                if descriptor.strengths:
                    st.write("주요 장점")
                    st.write("\n".join(f"- {item}" for item in descriptor.strengths))
                if descriptor.known_limitations:
                    st.write("알려진 한계")
                    st.write("\n".join(f"- {item}" for item in descriptor.known_limitations))


def _render_run_guidance(
    selected_parsers: list[str],
    parser_options: dict[str, dict[str, Any]],
) -> None:
    if "opendataloader" in selected_parsers:
        backend = parser_options.get("opendataloader", {}).get(
            "hybrid_backend", "off"
        )
        if backend == "off":
            st.warning(
                "OpenDataLoader가 local 모드로 설정되어 있습니다. 안내책자 PDF에서는 "
                "OCR이 없어 추출 텍스트가 거의 0개로 나오는 것이 정상에 가깝습니다."
            )
    if "mineru" in selected_parsers and shutil.which("mineru") is None:
        st.warning(
            "MinerU가 선택됐지만 현재 Streamlit 프로세스 PATH에서 사용할 수 없습니다. "
            "`.venv-mineru/bin`을 PATH에 넣고 서버를 다시 시작하기 전까지 MinerU는 실패합니다."
        )


def _render_qa_notice() -> None:
    st.info(
        "이 화면은 파서 출력만 비교합니다. 검색 품질 평가는 `retrieval-eval` CLI와 "
        "README의 NDCG 결과로 관리합니다."
    )


def _render_latest_results() -> None:
    summary = st.session_state.get("parser_comparison_summary")
    run_dir_value = st.session_state.get("parser_comparison_run_dir")
    if not summary or not run_dir_value:
        return

    run_dir = Path(run_dir_value)
    st.divider()
    st.subheader("최근 실행 결과")
    st.code(str(run_dir), language="text")
    _render_summary_interpretation(summary)

    parser_rows = [
        {
            "파서": _parser_label(parser_name),
            "성공": parser_summary["success_count"],
            "실패": parser_summary["failure_count"],
            "판정": _build_parser_run_verdict(parser_summary),
        }
        for parser_name, parser_summary in summary["per_parser"].items()
    ]
    st.dataframe(parser_rows, hide_index=True, width="stretch")

    comparison_rows = _load_comparison_rows(run_dir)
    if comparison_rows:
        st.subheader("문서별 비교")
        st.caption(
            "`기준 유사도`는 기준 파서 텍스트와의 유사도이지 품질 점수가 아닙니다. "
            "OCR이 필요한 PDF에서는 문자 수와 표 보존 여부가 더 중요합니다."
        )
        st.dataframe(comparison_rows, hide_index=True, width="stretch")

    manifest_path = run_dir / "run_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        with st.expander("실행 상세"):
            _render_manifest_details(manifest)
        with st.expander("개발자용 원본 JSON"):
            st.json(manifest)


def _load_comparison_rows(run_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for comparison_path in sorted((run_dir / "comparisons").glob("*.json")):
        payload = json.loads(comparison_path.read_text(encoding="utf-8"))
        document_id = payload["document_id"]
        for parser_name, parser_result in payload["parsers"].items():
            row: dict[str, Any] = {
                "문서": document_id,
                "파서": _parser_label(parser_name),
                "상태": _translate_status(parser_result["status"]),
                "판정": _build_document_verdict(parser_name, parser_result),
            }
            if parser_result["status"] == "success":
                parser_summary = parser_result["summary"]
                comparison = parser_result.get("comparison_to_baseline") or {}
                row.update(
                    {
                        "페이지": parser_summary["page_count"],
                        "문자 수": parser_summary["text_char_count"],
                        "텍스트 블록": parser_summary.get("text_block_count", 0),
                        "표": parser_summary.get("table_block_count", 0),
                        "기준 유사도": comparison.get("normalized_text_similarity"),
                    }
                )
            else:
                row["오류"] = parser_result.get("error")
            rows.append(row)
    return rows


def _parse_zero_based_page_range(raw: str) -> tuple[int, int] | None:
    stripped = raw.strip()
    if not stripped:
        return None
    if "-" not in stripped:
        value = int(stripped)
        return (value, value)
    start, end = stripped.split("-", 1)
    return (int(start), int(end))


def _build_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _render_summary_interpretation(summary: dict[str, Any]) -> None:
    if not summary.get("has_successful_baseline"):
        st.warning(
            "기준 파서가 성공하지 못했습니다. 이 실행에서는 기준 대비 비교가 유효하지 않습니다."
        )
    elif summary.get("overall_status") == "success":
        st.success("기준 파서가 성공했습니다. 비교 파서 결과를 기준 파서와 비교할 수 있습니다.")
    else:
        st.warning("일부 파서가 실패했습니다. 판정과 오류 컬럼을 확인하세요.")


def _render_manifest_details(manifest: dict[str, Any]) -> None:
    st.write(
        {
            "실행 이름": manifest.get("run_name"),
            "기준 파서": _parser_label(str(manifest.get("baseline_parser", ""))),
            "비교 파서": ", ".join(
                _parser_label(str(parser_name))
                for parser_name in manifest.get("candidate_parsers", [])
            ),
            "문서 디렉터리": manifest.get("document_dir"),
            "파일 패턴": manifest.get("file_glob"),
            "시작 시각": manifest.get("started_at"),
            "완료 시각": manifest.get("completed_at"),
        }
    )

    document_rows: list[dict[str, Any]] = []
    for document in manifest.get("documents", []):
        parsers = document.get("parsers", {})
        for parser_name, parser_result in parsers.items():
            parser_summary = parser_result.get("summary", {})
            document_rows.append(
                {
                    "문서": document.get("document_id"),
                    "파서": _parser_label(str(parser_name)),
                    "상태": _translate_status(str(parser_result.get("status", ""))),
                    "페이지": parser_summary.get("page_count"),
                    "문자 수": parser_summary.get("text_char_count"),
                    "텍스트 블록": parser_summary.get("text_block_count", 0),
                    "표 블록": parser_summary.get("table_block_count", 0),
                    "경고": parser_summary.get("warning_count", 0),
                    "오류": parser_result.get("error"),
                }
            )

    if document_rows:
        st.dataframe(document_rows, hide_index=True, width="stretch")


def _build_parser_run_verdict(parser_summary: dict[str, Any]) -> str:
    if parser_summary["failure_count"] and not parser_summary["success_count"]:
        return "실패"
    if parser_summary["failure_count"]:
        return "부분 성공"
    return "실행됨"


def _build_document_verdict(parser_name: str, parser_result: dict[str, Any]) -> str:
    if parser_result["status"] != "success":
        return "환경 또는 파서 오류"

    parser_summary = parser_result["summary"]
    text_chars = parser_summary["text_char_count"]
    table_count = parser_summary.get("table_block_count", 0)
    comparison = parser_result.get("comparison_to_baseline")

    if comparison is None:
        return "기준"
    if comparison.get("status") == "skipped":
        return "비교 안 됨"
    if text_chars == 0 and table_count == 0:
        return "나쁨: 텍스트/표 없음"
    if table_count > 0:
        return "유용함: 표 구조 추출"
    if text_chars > 0:
        return "유용함: 텍스트 추출"
    return "출력 확인 필요"


def _translate_status(status: str) -> str:
    if status == "success":
        return "성공"
    if status == "error":
        return "오류"
    return status


def _parser_label(parser_name: str) -> str:
    labels = {
        "pdfplumber": "pdfplumber 기준 파서",
        "pymupdf": "PyMuPDF 파서",
        "opendataloader": "OpenDataLoader-PDF",
        "mineru": "MinerU 파서",
    }
    label = labels.get(parser_name)
    if label is None:
        return parser_name
    return f"{label} ({parser_name})"


def _dedupe_preserving_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result

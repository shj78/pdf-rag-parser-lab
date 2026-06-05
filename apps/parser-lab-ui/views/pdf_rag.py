"""Single-PDF RAG page with parser selection."""

from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import streamlit as st

from src.chunkers.base import ChunkerConfig, ChunkingRequest
from src.chunkers.fixed_size_chunker import FixedSizeChunker
from src.parsers.factory import create_parser, list_parser_descriptors
from src.parsers.schemas import ParserConfig, ParseRequest
from src.schemas import Chunk, ParsedDocument, RetrievalResult
from views.retrieval_helpers import chunks_to_rows, results_to_rows, search_chunks

PROJECT_ROOT = Path(__file__).resolve().parents[3]
UPLOAD_DIR = PROJECT_ROOT / "artifacts" / "parser-lab-ui-uploads"
MINERU_BIN_DIR = PROJECT_ROOT / ".venv-mineru" / "bin"


def render_pdf_rag_page() -> None:
    """Render the primary PDF RAG workflow."""

    st.subheader("PDF 질문")

    descriptors = {descriptor.name: descriptor for descriptor in list_parser_descriptors()}
    parser_names = list(descriptors)
    selected_parser = st.selectbox(
        "파서",
        options=parser_names,
        index=_default_parser_index(parser_names),
        format_func=lambda name: descriptors[name].display_name,
    )

    parser_options = _render_parser_options(selected_parser)
    source = _render_pdf_source_selector()
    parse_tables = st.checkbox("표 추출", value=True)
    preserve_layout = st.checkbox("레이아웃 보존", value=True)

    if st.button("PDF 처리", type="primary", disabled=source is None):
        assert source is not None
        with st.spinner("PDF를 파싱하고 chunk를 만드는 중입니다..."):
            try:
                source_path = _materialize_pdf_source(source)
                parsed_document = _parse_pdf(
                    source_path=source_path,
                    parser_name=selected_parser,
                    parse_tables=parse_tables,
                    preserve_layout=preserve_layout,
                    parser_options=parser_options,
                )
                chunks = _chunk_document(parsed_document)
            except Exception as exc:
                st.error(_friendly_error_message(selected_parser, exc))
            else:
                st.session_state["rag_document"] = parsed_document
                st.session_state["rag_chunks"] = chunks
                st.session_state["rag_parser"] = selected_parser
                st.session_state["rag_source_path"] = str(source_path)
                if chunks:
                    st.success("처리 완료")
                else:
                    st.warning(
                        "PDF 처리는 끝났지만 검색 가능한 chunk가 없습니다. "
                        "텍스트 레이어가 없는 PDF라면 MinerU 또는 OpenDataLoader hybrid OCR을 선택하세요."
                    )

    parsed_document = st.session_state.get("rag_document")
    chunks = st.session_state.get("rag_chunks", [])
    if not parsed_document:
        return

    _render_document_summary(parsed_document, chunks)
    _render_question_panel(chunks)


def _render_pdf_source_selector() -> dict[str, Any] | None:
    uploaded_file = st.file_uploader("PDF 업로드", type=["pdf"])
    if uploaded_file is None:
        return None
    return {
        "mode": "upload",
        "filename": uploaded_file.name,
        "contents": uploaded_file.getvalue(),
    }


def _render_parser_options(parser_name: str) -> dict[str, Any]:
    options: dict[str, Any] = {}

    if parser_name == "mineru":
        with st.expander("MinerU 옵션"):
            if shutil.which("mineru") is None:
                if (MINERU_BIN_DIR / "mineru").exists():
                    st.info("로컬 `.venv-mineru/bin/mineru`를 자동으로 사용합니다.")
                else:
                    st.warning(
                        "현재 Streamlit 프로세스 PATH에서 MinerU CLI를 찾을 수 없습니다."
                    )
            options["backend"] = st.text_input("백엔드", value="pipeline")
            options["language"] = st.text_input("언어", value="korean")
            page_range = st.text_input(
                "페이지 범위",
                value="",
                help="0-indexed입니다. 예: 0-2는 PDF 1~3페이지입니다. 비워두면 전체 PDF를 처리합니다.",
            )
            parsed_page_range = _parse_zero_based_page_range(page_range)
            if parsed_page_range is not None:
                options["page_range"] = parsed_page_range

    if parser_name == "opendataloader":
        with st.expander("OpenDataLoader 옵션"):
            options["cli_path"] = st.text_input(
                "CLI 경로",
                value=str(PROJECT_ROOT / ".venv-opendataloader/bin/opendataloader-pdf"),
            )
            hybrid_backend = st.selectbox(
                "하이브리드 백엔드",
                options=["off", "docling-fast", "hancom-ai"],
            )
            options["hybrid_backend"] = hybrid_backend
            if hybrid_backend != "off":
                options["hybrid_url"] = st.text_input(
                    "하이브리드 URL",
                    value="http://127.0.0.1:5002",
                )
                options["hybrid_mode"] = st.selectbox(
                    "하이브리드 모드",
                    options=["auto", "full"],
                )
            pages = st.text_input("페이지", value="", help="예: 1-3")
            if pages.strip():
                options["pages"] = pages.strip()

    return options


def _parse_pdf(
    *,
    source_path: Path,
    parser_name: str,
    parse_tables: bool,
    preserve_layout: bool,
    parser_options: dict[str, Any],
) -> ParsedDocument:
    _prepare_parser_environment(parser_name)
    parser_config = ParserConfig(
        parser_name=parser_name,
        parse_tables=parse_tables,
        preserve_layout=preserve_layout,
        extra_options=parser_options,
    )
    parser = create_parser(parser_name, config=parser_config)
    parser.validate_environment()
    return parser.parse(
        ParseRequest(
            document_id=source_path.stem,
            source_path=source_path,
            config=parser_config,
        )
    )


def _prepare_parser_environment(parser_name: str) -> None:
    if parser_name != "mineru":
        return
    if shutil.which("mineru") is not None:
        return
    mineru_bin = MINERU_BIN_DIR / "mineru"
    if mineru_bin.exists():
        os.environ["PATH"] = f"{MINERU_BIN_DIR}{os.pathsep}{os.environ.get('PATH', '')}"


def _chunk_document(document: ParsedDocument) -> list[Chunk]:
    chunker = FixedSizeChunker()
    return chunker.chunk(
        ChunkingRequest(
            document=document,
            config=ChunkerConfig(
                chunker_name=chunker.name,
                target_chunk_size=800,
                overlap=120,
                parser_name=document.parser_name,
                extra_options={
                    "prepend_page_text_to_tables": True,
                    "table_context_strategy": "calendar_month",
                },
            ),
        )
    )


def _render_document_summary(document: ParsedDocument, chunks: list[Chunk]) -> None:
    text_blocks = sum(len(page.text_blocks) for page in document.pages)
    table_blocks = sum(len(page.table_blocks) for page in document.pages)
    chars = sum(len(chunk.text) for chunk in chunks)

    cols = st.columns(5)
    cols[0].metric("파서", document.parser_name)
    cols[1].metric("페이지", len(document.pages))
    cols[2].metric("텍스트 블록", text_blocks)
    cols[3].metric("표 블록", table_blocks)
    cols[4].metric("Chunks", len(chunks))

    if document.warnings:
        with st.expander("파서 경고"):
            for warning in document.warnings:
                st.warning(warning)

    if not chunks:
        st.warning(
            "이 파서 결과에는 검색 가능한 텍스트나 표 내용이 없습니다. "
            "파서 선택을 바꾸거나 OCR 옵션을 켠 뒤 다시 처리하세요."
        )

    with st.expander("Chunk 미리보기"):
        st.caption(f"검색 대상 문자 수: {chars}")
        st.dataframe(chunks_to_rows(chunks[:80]), hide_index=True, width="stretch")


def _render_question_panel(chunks: list[Chunk]) -> None:
    if not chunks:
        st.warning("검색 가능한 chunk가 없습니다. 다른 파서나 OCR 옵션을 선택하세요.")
        return

    st.divider()
    query = st.text_area("질문", value="", height=90)
    top_k = st.number_input("근거 수", min_value=1, max_value=20, value=8)

    if st.button("질문하기", type="primary", disabled=not query.strip()):
        try:
            results = _search_for_answer(
                chunks,
                query=query,
                top_k=int(top_k),
            )
        except Exception as exc:
            st.error(f"{type(exc).__name__}: {exc}")
            return
        if not results:
            st.warning("관련 근거를 찾지 못했습니다.")
            return
        if any(result.metadata.get("retrieval_fallback") for result in results):
            st.info(
                "정확히 겹치는 검색어가 없어 완화 검색으로 근거 후보를 가져왔습니다. "
                "질문 단어와 PDF OCR/표기 방식이 다를 때 발생합니다."
            )

        context = _build_context(results)
        with st.spinner("답변을 만드는 중입니다..."):
            try:
                answer = _generate_answer(query, context, results)
            except Exception as exc:
                st.error(f"{type(exc).__name__}: {exc}")
                answer = _build_grounded_answer(results)

        st.subheader("답변")
        st.write(answer)
        st.subheader("근거")
        st.dataframe(results_to_rows(results), hide_index=True, width="stretch")


def _build_context(results: list[RetrievalResult], *, max_chars: int = 6000) -> str:
    lines: list[str] = []
    for index, result in enumerate(results, start=1):
        preview = str(result.metadata.get("text_preview") or "").strip()
        if not preview:
            continue
        lines.append(
            f"[{index}] parser={result.parser_name}, page={result.page_number}, "
            f"chunk={result.chunk_id}\n{preview}"
        )
    return "\n\n".join(lines)[:max_chars]


def _search_for_answer(
    chunks: list[Chunk],
    *,
    query: str,
    top_k: int,
) -> list[RetrievalResult]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return search_chunks(chunks, query=query, top_k=top_k)
    return search_chunks(
        chunks,
        query=query,
        top_k=top_k,
        index_backend="embedding_in_memory",
        embedding_provider="openai",
        embedding_model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
        embedding_options={"api_key": api_key},
    )


def _build_grounded_answer(results: list[RetrievalResult]) -> str:
    lines = ["상위 검색 근거입니다."]
    for index, result in enumerate(results[:3], start=1):
        preview = str(result.metadata.get("text_preview") or "").strip()
        if preview:
            lines.append(f"[{index}] {preview}")
    return "\n\n".join(lines)


def _generate_answer(
    query: str,
    context: str,
    results: list[RetrievalResult],
) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        return _generate_openai_answer(query, context, api_key)
    if os.getenv("OLLAMA_BASE"):
        return _generate_ollama_answer(query, context)
    return _build_grounded_answer(results)


def _generate_openai_answer(query: str, context: str, api_key: str) -> str:
    prompt = f"""너는 PDF 문서 내용을 기반으로 답변하는 RAG 어시스턴트다.

규칙:
- 아래 Context에 포함된 정보만 사용한다.
- 근거가 부족하면 문서에서 확인할 수 없다고 말한다.
- 답변 끝에 사용한 근거 번호를 [1], [2]처럼 표시한다.

Context:
{context}

Question:
{query}
"""
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini"),
        messages=[{"role": "user", "content": prompt}],
        timeout=60,
    )
    return (response.choices[0].message.content or "").strip()


def _generate_ollama_answer(query: str, context: str) -> str:
    import requests

    prompt = f"""너는 PDF 문서 내용을 기반으로 답변하는 RAG 어시스턴트다.

규칙:
- 아래 Context에 포함된 정보만 사용한다.
- 근거가 부족하면 문서에서 확인할 수 없다고 말한다.
- 답변 끝에 사용한 근거 번호를 [1], [2]처럼 표시한다.

Context:
{context}

Question:
{query}
"""
    response = requests.post(
        f"{os.getenv('OLLAMA_BASE', 'http://localhost:11434')}/api/generate",
        json={
            "model": os.getenv("OLLAMA_CHAT_MODEL", "llama3.1"),
            "prompt": prompt,
            "stream": False,
        },
        timeout=120,
    )
    response.raise_for_status()
    return str(response.json().get("response", "")).strip()


def _save_uploaded_file(filename: str, contents: bytes) -> Path:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = Path(filename).name
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    target_path = UPLOAD_DIR / f"{timestamp}-{safe_name}"
    target_path.write_bytes(contents)
    return target_path


def _materialize_pdf_source(source: dict[str, Any]) -> Path:
    return _save_uploaded_file(str(source["filename"]), bytes(source["contents"]))


def _default_parser_index(parser_names: list[str]) -> int:
    if "mineru" in parser_names and (MINERU_BIN_DIR / "mineru").exists():
        return parser_names.index("mineru")
    if "pdfplumber" in parser_names:
        return parser_names.index("pdfplumber")
    return 0


def _friendly_error_message(parser_name: str, exc: Exception) -> str:
    message = str(exc)
    if parser_name == "mineru" and "CLI not found" in message:
        return (
            "MinerU 실행 파일을 찾지 못했습니다. `.venv-mineru`가 설치되어 있는지 확인하거나 "
            "다른 파서를 선택하세요."
        )
    if parser_name == "opendataloader" and "hybrid backend" in message:
        return (
            "OpenDataLoader hybrid backend에 연결하지 못했습니다. hybrid OCR을 쓰려면 "
            "`opendataloader-pdf-hybrid` 서버를 먼저 띄우거나 backend를 off로 바꾸세요."
        )
    return f"{type(exc).__name__}: {message}"


def _parse_zero_based_page_range(raw: str) -> tuple[int, int] | None:
    stripped = raw.strip()
    if not stripped:
        return None
    if "-" not in stripped:
        value = int(stripped)
        return (value, value)
    start, end = stripped.split("-", 1)
    return (int(start), int(end))

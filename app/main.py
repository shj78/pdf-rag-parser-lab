import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Annotated, Any, Dict, List
from uuid import uuid4

import pdfplumber
import requests
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from langsmith import traceable
from pydantic import BaseModel, field_validator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from .config import (
    ALLOWED_EXTENSIONS,
    OLLAMA_BASE,
    OLLAMA_CHAT_MODEL,
    OPENAI_API_KEY,
    OPENAI_CHAT_MODEL,
    PROVIDER,
    TRACE_DIR,
    UPLOAD_DIR,
)
from .embedding_utils import (
    get_embedding,
    get_embeddings_batch_ollama,
    split_text,
)
from .exceptions import (
    FileSystemError,
    LLMError,
    PDFProcessingError,
    RAGException,
    RerankerError,
    filesystem_error_context,
    ollama_error_context,
    openai_error_context,
)
from .supabase_utils import save_embedding, search_similar_embeddings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="DocuFlow AI Agent")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.exception_handler(RAGException)
async def rag_exception_handler(_request: Request, exc: RAGException) -> JSONResponse:
    logger.error("[%s] %s | detail=%s", type(exc).__name__, exc.message, exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.exception_handler(Exception)
async def generic_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    logger.error("처리되지 않은 예외: %s", str(exc), exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "내부 서버 오류가 발생했습니다. 잠시 후 다시 시도해주세요."},
    )


@app.exception_handler(404)
async def not_found_handler(_request: Request, _exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=404, content={"detail": "요청하신 경로를 찾을 수 없습니다."}
    )


_allowed_origins = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:8000,http://localhost:7860",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
UploadFileParam = Annotated[UploadFile, File(...)]


_UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_MAX_QUERY_LENGTH = 2000


class DocumentIdBody(BaseModel):
    document_id: str


class QuestionBody(BaseModel):
    document_id: str
    query: str
    use_rerank: bool = False

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("질문 내용이 비어 있습니다.")
        if len(stripped) > _MAX_QUERY_LENGTH:
            raise ValueError(
                f"질문이 너무 깁니다. 최대 {_MAX_QUERY_LENGTH}자까지 입력 가능합니다."
            )
        return stripped

    @field_validator("document_id")
    @classmethod
    def validate_document_id(cls, v: str) -> str:
        if not _UUID_PATTERN.match(v.strip()):
            raise ValueError("document_id는 유효한 UUID 형식이어야 합니다.")
        return v.strip()


conversation_history: Dict[str, list] = {}  # document_id -> [{"q": "...", "a": "..."}]
""" 재질문 상태 관리 """
pending_clarifications: Dict[str, Dict[str, Any]] = {}

HISTORY_WINDOW_TURNS = 4
TOP_K = 30
SIMILARITY_THRESHOLD = 0.4
MAX_CLARIFICATION_ATTEMPTS = 2
RERANKER_TOP_N = 5
RERANKER_MODEL_NAME = "BAAI/bge-reranker-v2-m3"
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB
CHUNK_SIZE = 256
CHUNK_OVERLAP = 30

_reranker = None  # 최초 호출 시 lazy load


def get_reranker():
    global _reranker
    if _reranker is None:
        try:
            from sentence_transformers import CrossEncoder

            _reranker = CrossEncoder(RERANKER_MODEL_NAME)
        except Exception as e:
            error_msg = str(e).lower()
            if (
                "memory" in error_msg
                or "oom" in error_msg
                or "out of memory" in error_msg
            ):
                raise RerankerError(
                    "리랭커 모델 로딩 중 메모리가 부족합니다.", detail=str(e)
                ) from e
            raise RerankerError(
                f"리랭커 모델({RERANKER_MODEL_NAME})을 불러올 수 없습니다.",
                detail=str(e),
            ) from e
    return _reranker


def rerank_chunks(
    query: str, chunks: List[Dict[str, Any]], top_n: int = RERANKER_TOP_N
) -> List[Dict[str, Any]]:
    """Cross-Encoder로 청크를 재정렬하고 상위 top_n개를 반환한다."""
    if not chunks:
        return chunks
    try:
        reranker = get_reranker()
        pairs = [(query, chunk["content"]) for chunk in chunks]
        scores = reranker.predict(pairs)
        ranked = sorted(
            zip(chunks, scores, strict=False), key=lambda x: x[1], reverse=True
        )
        return [chunk for chunk, _ in ranked[:top_n]]
    except RerankerError:
        raise
    except Exception as e:
        raise RerankerError("리랭킹 처리 중 오류가 발생했습니다.", detail=str(e)) from e


# 템플릿 및 정적 파일 설정
templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def extract_text_from_pdf(file_path: str) -> str:
    """
    [TODO Day 1] PDF 파일에서 텍스트를 추출하는 함수입니다.

    요구사항:
    1. PDF에서 텍스트를 추출할 수 있는 방법을 직접 조사하여 구현하세요.
       - 어떤 라이브러리를 사용할지는 스스로 결정하세요.
         (Pipfile에 설치된 패키지를 확인하세요.)
    2. 모든 페이지의 텍스트를 추출하여 하나의 문자열로 합치세요.
    """
    # ---------------------------------------------------------
    # [Day 1] 과제: PDF 텍스트 추출 로직 작성
    # ---------------------------------------------------------
    texts = []

    try:
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                # 표 영역의 bbox를 수집
                tables = page.extract_tables()
                table_bboxes = [table_obj.bbox for table_obj in page.find_tables()]

                # 표 영역을 제외한 일반 텍스트 추출
                if table_bboxes:
                    non_table_page = page
                    for bbox in table_bboxes:
                        non_table_page = non_table_page.outside_bbox(bbox)
                    page_text = non_table_page.extract_text()
                else:
                    page_text = page.extract_text()

                if page_text:
                    texts.append(page_text)

                # 표를 마크다운 형식으로 변환
                for table in tables:
                    rows = []
                    for i, row in enumerate(table):
                        cells = [
                            str(cell).strip() if cell is not None else ""
                            for cell in row
                        ]
                        rows.append("| " + " | ".join(cells) + " |")
                        if i == 0:
                            rows.append("| " + " | ".join(["---"] * len(cells)) + " |")
                    texts.append("\n".join(rows))
    except PDFProcessingError:
        raise
    except Exception as e:
        error_msg = str(e).lower()
        if "password" in error_msg or "encrypted" in error_msg:
            raise PDFProcessingError(
                "비밀번호로 보호된 PDF는 처리할 수 없습니다.", detail=str(e)
            ) from e
        raise PDFProcessingError(
            "PDF 파일을 열거나 읽는 중 오류가 발생했습니다. 파일이 손상되었을 수 있습니다.",
            detail=str(e),
        ) from e

    full_text = "\n\n".join(texts).strip()

    if not full_text:
        raise PDFProcessingError(
            "PDF에서 텍스트를 추출할 수 없습니다. 이미지 전용 PDF이거나 내용이 없는 파일입니다."
        )

    return full_text


async def _build_and_store_clarification(
    document_id: str,
    original_query: str,
    history_window: List[Dict[str, str]],
) -> str:
    """재질문을 생성하고 pending 상태로 저장한 뒤 재질문 문자열을 반환한다."""
    clarifying_question = await build_clarifying_question(
        document_id, original_query, history_window
    )
    store_pending_clarification(document_id, original_query, clarifying_question)
    return clarifying_question


def get_history_window(
    document_id: str, max_turns: int = HISTORY_WINDOW_TURNS
) -> List[Dict[str, str]]:
    history = conversation_history.get(document_id, [])
    if max_turns <= 0:
        return []
    return history[-max_turns:]


def format_history(history: List[Dict[str, str]]) -> str:
    if not history:
        return "(이전 대화 없음)"
    return "\n".join(
        [
            f"Q: {item['q']}\nA: {item['a']}"
            for item in history
            if "q" in item and "a" in item
        ]
    )


@traceable(run_type="llm", name="call_llm")
async def call_llm(prompt: str, *, timeout: int = 60, expect_json: bool = False) -> Any:
    if PROVIDER == "openai":
        from openai import AsyncOpenAI

        with openai_error_context(timeout=timeout, error_class=LLMError):
            client = AsyncOpenAI(api_key=OPENAI_API_KEY)
            kwargs: Dict[str, Any] = {
                "model": OPENAI_CHAT_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "timeout": timeout,
            }
            if expect_json:
                kwargs["response_format"] = {"type": "json_object"}
            response = await client.chat.completions.create(**kwargs)
            content = (response.choices[0].message.content or "").strip()
            if not content:
                raise LLMError("OpenAI가 빈 응답을 반환했습니다.")
            if expect_json:
                try:
                    return json.loads(content)
                except json.JSONDecodeError as e:
                    raise LLMError(
                        "OpenAI 응답을 JSON으로 파싱할 수 없습니다.",
                        detail=content[:200],
                    ) from e
            return content

    else:

        def _sync_ollama() -> Any:
            with ollama_error_context(timeout=timeout, error_class=LLMError):
                request_body: Dict[str, Any] = {
                    "model": OLLAMA_CHAT_MODEL,
                    "prompt": prompt,
                    "stream": False,
                }
                if expect_json:
                    request_body["format"] = "json"
                response = requests.post(
                    f"{OLLAMA_BASE}/api/generate",
                    json=request_body,
                    timeout=timeout,
                )
                response.raise_for_status()
                content = response.json().get("response", "").strip()
                if not content:
                    raise LLMError("Ollama가 빈 응답을 반환했습니다.")
                if expect_json:
                    try:
                        return json.loads(content)
                    except json.JSONDecodeError as e:
                        raise LLMError(
                            "Ollama 응답을 JSON으로 파싱할 수 없습니다.",
                            detail=content[:200],
                        ) from e
                return content

        return await asyncio.to_thread(_sync_ollama)


@traceable(run_type="chain", name="classify_query")
async def classify_query(document_id: str, user_query: str) -> str:
    history = get_history_window(document_id)

    self_contained_prompt = f"""너의 역할은 현재 질문이 이전 대화 없이도 완전히 이해 가능한지 판정하는 것이다.

최근 대화:
{format_history(history)}

현재 질문:
{user_query}

규칙:
- 가장 먼저 "이 질문이 이전 대화 없이도 완전히 이해되는가?"를 판단한다.
- 질문 안의 대상, 범위, 순서, 비교 기준, 수량 조건이 이전 대화 없이는 확정되지 않으면 SELF_CONTAINED가 아니다.
- 최근 대화를 보면 해소되지만, 최근 대화가 없으면 "그중", "첫 번째", "그 항목", "위 내용", "이 경우" 같은 표현은 SELF_CONTAINED가 아닐 가능성이 높다.
- 문서 안 어딘가에 있을 법하다는 이유만으로 SELF_CONTAINED라고 판단하지 않는다.
- 질문 문자열만 보고도 무엇을 요구하는지 충분히 특정되면 SELF_CONTAINED다.
- 추측하지 말고 가장 보수적으로 판정한다.

반드시 JSON 하나만 반환한다.
{{"self_contained":true}}
"""

    self_contained_result = await call_llm(
        self_contained_prompt, timeout=60, expect_json=True
    )
    self_contained = bool(self_contained_result.get("self_contained", False))

    if history and not self_contained:
        return "FOLLOW_UP"

    classification_prompt = f"""너의 역할은 업로드된 단일 문서에 대한 RAG 질문을 아래 3가지 유형 중 하나로 분류하는 것이다.

최근 대화:
{format_history(history)}

현재 질문:
{user_query}

분류 기준:
- STANDALONE: 이전 대화 없이도 질문의 대상, 범위, 요구사항이 충분히 해석 가능한 독립 질문
- NEEDS_CLARIFICATION: 이전 대화를 보더라도 대상, 범위, 항목이 부족해 먼저 되물어야 하는 질문
- OUT_OF_SCOPE: 업로드된 문서만으로는 답할 수 없는 외부 세계 질문이나 문서와 명백히 무관한 요청

규칙:
- 이 단계에서는 FOLLOW_UP을 사용하지 않는다. self-contained가 아닌 질문은 이미 앞 단계에서 걸러졌다고 가정한다.
- history가 없더라도 질문 자체가 모호하면 NEEDS_CLARIFICATION이다.
- 특정 도메인을 가정하지 말고, 어떤 PDF든 업로드될 수 있다고 가정한다.
- 사용자가 문서 내용 요약, 특정 조항, 표, 수치, 정의를 묻는 경우는 우선 문서 질의로 본다.
- 현재 시세, 실시간 뉴스, 일반 상식처럼 문서 밖 정보가 필요한 경우만 OUT_OF_SCOPE로 분류한다.
- 문서 질의처럼 보인다는 이유만으로 STANDALONE으로 두지 말고, 질문 자체의 완결성을 우선한다.
- 추측하지 말고 가장 보수적으로 분류한다.

반드시 JSON 하나만 반환한다.
{{"status":"STANDALONE|NEEDS_CLARIFICATION|OUT_OF_SCOPE"}}
"""
    result = await call_llm(classification_prompt, timeout=60, expect_json=True)
    status = result.get("status", "NEEDS_CLARIFICATION").strip()
    if status not in {"STANDALONE", "NEEDS_CLARIFICATION", "OUT_OF_SCOPE"}:
        status = "NEEDS_CLARIFICATION"
    return status


async def build_clarifying_question(
    document_id: str, user_query: str, history: List[Dict[str, str]] | None = None
) -> str:
    recent_history = history if history is not None else get_history_window(document_id)
    clarification_prompt = f"""너의 역할은 문서 기반 RAG에서 사용자에게 재질문 1문장을 만드는 것이다.

최근 대화:
{format_history(recent_history)}

현재 질문:
{user_query}

규칙:
- 반드시 1문장으로 작성한다.
- 가능하면 A/B 선택지 형태로 작성한다.
- "더 구체적으로 말씀해주세요" 같은 추상 표현은 금지한다.
- 최근 대화에서 확인 가능한 대상만 사용한다.
- 대화만으로도 선택지를 만들 수 없으면, 무엇이 필요한지 구체적으로 묻는다.

출력은 JSON 하나만 반환한다.
{{"clarifying_question":"..."}}
"""
    result = await call_llm(clarification_prompt, timeout=60, expect_json=True)
    return result["clarifying_question"].strip()


async def rewrite_query_with_history(
    document_id: str, user_query: str
) -> Dict[str, str]:
    history = get_history_window(document_id)
    if not history:
        return {"status": "REWRITTEN", "rewritten_query": user_query}

    rewrite_prompt = f"""너의 역할은 후속 질문을 독립적인 질문으로 재작성하는 것이다.

최근 대화:
{format_history(history)}

현재 질문:
{user_query}

규칙:
- 현재 질문의 대상이 최근 대화로 명확히 특정되면 rewritten_query를 만든다.
- 최근 대화만으로 대상, 범위, 시점, 항목을 특정할 수 없으면 절대 추측하지 않는다.
- 문서 내용으로 추정하지 말고, 오직 최근 대화만 사용한다.
- 재작성된 질문은 대화 이력 없이도 이해되어야 한다.
- 현재 질문의 지시어를 해소하되, 원문에 있는 정보는 절대 삭제하지 않는다.
- 수량, 순서, 범위, 비교 조건을 반드시 보존한다.
- 재작성된 질문은 원문의 의미와 요구사항이 동일해야 한다.

출력은 아래 JSON 하나만 반환한다.
1. 재작성 가능할 때
{{"status":"REWRITTEN","rewritten_query":"..."}}

2. 재작성 불가능할 때
{{"status":"NEEDS_CLARIFICATION"}}
"""
    result = await call_llm(rewrite_prompt, timeout=60, expect_json=True)

    if result["status"] == "REWRITTEN":
        return {
            "status": "REWRITTEN",
            "rewritten_query": result["rewritten_query"].strip(),
        }

    return {
        "status": "NEEDS_CLARIFICATION",
        "rewritten_query": None,
    }


def store_pending_clarification(
    document_id: str,
    original_query: str,
    clarifying_question: str,
) -> None:
    previous_attempts = pending_clarifications.get(document_id, {}).get(
        "attempt_count", 0
    )
    pending_clarifications[document_id] = {
        "state": "AWAITING_CLARIFICATION",
        "original_query": original_query,
        "clarifying_question": clarifying_question,
        "attempt_count": previous_attempts + 1,
    }


def clear_pending_clarification(document_id: str) -> None:
    pending_clarifications.pop(document_id, None)


async def merge_clarification_answer(
    document_id: str, user_reply: str
) -> Dict[str, str]:
    pending = pending_clarifications.get(document_id)
    if not pending:
        return {"status": "NO_PENDING", "merged_query": user_reply}

    merge_prompt = f"""너의 역할은 원래 질문과 보충 답변을 합쳐 독립적인 완성 질문 하나를 만드는 것이다.

원래 질문:
{pending["original_query"]}

재질문:
{pending["clarifying_question"]}

사용자 보충 답변:
{user_reply}

규칙:
- 완성 질문은 대화 이력 없이도 이해되어야 한다.
- 보충 답변만 단독으로 쓰지 말고 원래 질문의 목적을 반드시 유지한다.
- 여전히 모호하면 추측하지 말고 incomplete를 true로 둔다.

JSON 하나만 반환한다.
{{"merged_query":"...","incomplete":false}}
"""
    result = await call_llm(merge_prompt, timeout=60, expect_json=True)
    merged_query = result.get("merged_query", "").strip()
    incomplete = bool(result.get("incomplete", False))
    return {
        "status": "NEEDS_CLARIFICATION" if incomplete or not merged_query else "MERGED",
        "merged_query": merged_query or pending["original_query"],
    }


def should_force_progress(document_id: str) -> bool:
    pending = pending_clarifications.get(document_id, {})
    return pending.get("attempt_count", 0) >= MAX_CLARIFICATION_ATTEMPTS


def has_any_results(similar_chunks: List[Dict[str, Any]]) -> bool:
    return bool(similar_chunks)


def top_similarity(similar_chunks: List[Dict[str, Any]]) -> float | None:
    return similar_chunks[0]["similarity"] if similar_chunks else None


@traceable(run_type="retriever", name="retrieve_chunks")
async def retrieve_chunks(
    document_id: str, search_query: str, embedding: List[float] | None = None
) -> Dict[str, Any]:
    query_embedding = (
        embedding if embedding is not None else await get_embedding(search_query)
    )
    similar_chunks = await asyncio.to_thread(
        search_similar_embeddings,
        query_embedding,
        document_id,
        TOP_K,
        SIMILARITY_THRESHOLD,
    )
    return {
        "embedding": query_embedding,
        "chunks": similar_chunks,
    }


@traceable(run_type="llm", name="generate_answer")
async def generate_answer(context: str, search_query: str) -> str:
    answer_prompt = f"""[역할]
- 너는 업로드된 문서를 바탕으로만 답변하는 엄격한 RAG 어시스턴트다.

[행동 지침]
- 반드시 아래 Context에 포함된 정보만 사용한다.
- 근거가 부족하면 추측하지 말고 "문서에서 확인할 수 없습니다."라고 답한다.
- 질문이 여러 해석으로 갈리면 하나를 임의 선택하지 말고 왜 모호한지 짧게 밝힌다.
- 답변 끝에는 근거가 된 passage index를 대괄호로 표기한다.
- 마크다운 문법(**, *, #, ─ 등)을 사용하지 않고 일반 텍스트로만 답변한다.

Context:
{context}

Question:
{search_query}

"""
    return await call_llm(answer_prompt, timeout=120, expect_json=False)


_MAX_CONVERSATION_SESSIONS = 50


def append_history(document_id: str, user_query: str, answer: str) -> None:
    if (
        document_id not in conversation_history
        and len(conversation_history) >= _MAX_CONVERSATION_SESSIONS
    ):
        oldest_key = next(iter(conversation_history))
        conversation_history.pop(oldest_key, None)
        logger.warning("대화 세션 한도 초과, 가장 오래된 세션 삭제: %s", oldest_key)
    history = conversation_history.get(document_id, [])
    history.append({"q": user_query, "a": answer})
    conversation_history[document_id] = history


def persist_trace_record(record: Dict[str, Any]) -> str:
    trace_file_path = os.path.join(TRACE_DIR, "qa_trace_log.jsonl")
    try:
        with open(trace_file_path, "a", encoding="utf-8") as trace_file:
            trace_file.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as e:
        # 트레이스 쓰기 실패는 비치명적 — 유저 응답을 방해하지 않음
        logger.error("트레이스 기록 저장 실패 (무시하고 계속): %s", str(e))
    return trace_file_path


@app.get("/health")
async def health_check() -> JSONResponse:
    status: Dict[str, Any] = {"status": "healthy", "checks": {}}
    http_status = 200

    # Supabase DB 연결 확인
    try:
        from .supabase_utils import supabase as _supabase

        _supabase.table("document_chunks").select("id").limit(1).execute()
        status["checks"]["database"] = "ok"
    except Exception as e:
        status["checks"]["database"] = f"error: {str(e)}"
        status["status"] = "degraded"
        http_status = 503

    # LLM 서버 연결 확인
    if PROVIDER == "ollama":
        try:
            resp = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=5)
            resp.raise_for_status()
            status["checks"]["llm"] = "ok"
        except Exception as e:
            status["checks"]["llm"] = f"error: {str(e)}"
            status["status"] = "degraded"
            http_status = 503
    else:
        status["checks"]["llm"] = "openai (연결 확인 생략)"

    return JSONResponse(content=status, status_code=http_status)


@app.get("/", response_class=HTMLResponse)
async def root_page(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/documents/")
@limiter.limit("10/minute")
async def upload_document(request: Request, file: UploadFileParam):
    """
    [TODO Day 1 & 2] 문서 업로드 및 임베딩 처리 엔드포인트

    프로세스:
    1. 업로드된 파일을 로컬(UPLOAD_DIR)에 저장
    2. PDF에서 텍스트 추출
    3. 텍스트를 청크로 분할
    4. 각 청크를 임베딩하고 DB에 저장
    5. (Deep Dive) 대량의 청크를 처리할 때 속도 저하를 막기 위한 방법을 조사해보세요.
       힌트: Python의 비동기 처리 방식을 검토해보세요.
    """

    document_id = str(uuid4())

    try:
        # ---------------------------------------------------------
        # [Day 1 & 2] 과제: 파이프라인 구현
        # 1. 파일 저장
        # 2. 텍스트 추출
        # 3. 청크 분할
        # 4. 임베딩 및 저장
        # ---------------------------------------------------------
        if not file.filename or not allowed_file(file.filename):
            raise HTTPException(
                status_code=400, detail="PDF 파일만 업로드할 수 있습니다."
            )

        contents = await file.read()
        if len(contents) > MAX_UPLOAD_SIZE:
            raise HTTPException(
                status_code=413,
                detail="파일 크기가 너무 큽니다. 최대 10MB까지 업로드 가능합니다.",
            )

        safe_filename = f"{uuid4().hex}.pdf"
        file_path = os.path.join(UPLOAD_DIR, safe_filename)
        with filesystem_error_context(error_class=FileSystemError, fatal=True):
            with open(file_path, "wb") as buffer:
                buffer.write(contents)

        raw_text = extract_text_from_pdf(file_path)
        chunks = split_text(raw_text, CHUNK_SIZE, CHUNK_OVERLAP)
        logger.info("[청크 수] %d개", len(chunks))

        batch_start = time.perf_counter()
        embeddings = await get_embeddings_batch_ollama(chunks)
        batch_elapsed = time.perf_counter() - batch_start
        logger.info(
            "[임베딩] %.3fs (%d개, 평균 %.1fms/청크)",
            batch_elapsed,
            len(chunks),
            batch_elapsed / len(chunks) * 1000,
        )

        for chunk_index, embedding in enumerate(embeddings):
            save_embedding(document_id, chunks[chunk_index], embedding, chunk_index)

        logger.info("[Document ID] %s", document_id)

        return {
            "message": "문서 처리가 완료되었습니다.",
            "document_id": document_id,
            "chunks_count": len(chunks),
        }

    except HTTPException:
        raise
    except RAGException:
        raise  # 전역 핸들러로 위임
    except Exception as e:
        logger.error("문서 처리 중 예기치 않은 오류: %s", str(e))
        raise HTTPException(
            status_code=500,
            detail="문서 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
        ) from e


@app.post("/qa")
@limiter.limit("30/minute")
async def question_answering(request: Request, question: QuestionBody):
    """RAG 기반 질의응답 엔드포인트"""

    try:
        trace: List[Dict[str, Any]] = []
        started_at = time.perf_counter()
        trace_id = str(uuid4())

        def add_trace(step: str, detail: str, **extra: Any) -> None:
            trace_item: Dict[str, Any] = {
                "step": step,
                "detail": detail,
                "elapsed_ms": round((time.perf_counter() - started_at) * 1000, 1),
            }
            trace_item.update(extra)
            trace.append(trace_item)

        def build_trace_record(
            *,
            final_status: str,
            answer: str,
            search_query: str | None = None,
            sources: List[Dict[str, Any]] | None = None,
        ) -> Dict[str, Any]:
            return {
                "trace_id": trace_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "document_id": document_id,
                "user_query": user_query,
                "search_query": search_query,
                "final_status": final_status,
                "answer": answer,
                "sources": sources or [],
                "trace": trace,
            }

        def persist_and_respond(
            *,
            final_status: str,
            answer: str,
            search_query: str | None = None,
            sources: List[Dict[str, Any]] | None = None,
        ) -> Dict[str, Any]:
            record = build_trace_record(
                final_status=final_status,
                answer=answer,
                search_query=search_query,
                sources=sources,
            )
            trace_file = persist_trace_record(record)
            return {
                "answer": answer,
                "sources": sources or [],
                "debug_trace": trace,
                "trace_id": trace_id,
                "trace_file": trace_file,
            }

        document_id = question.document_id
        user_query = question.query.strip()
        use_rerank = question.use_rerank
        history_window = get_history_window(document_id)
        search_query = user_query
        embedded_question: List[float] | None = None
        similar_chunks: List[Dict[str, Any]] = []
        add_trace(
            "request_received",
            "질문 요청을 수신했습니다.",
            document_id=document_id,
            user_query=user_query,
            history_turns=len(history_window),
        )

        pending = pending_clarifications.get(document_id)
        if pending:
            add_trace(
                "pending_clarification_found",
                "기존 재질문 대기 상태를 확인했습니다.",
                original_query=pending["original_query"],
                attempt_count=pending["attempt_count"],
            )
            merge_result = await merge_clarification_answer(document_id, user_query)
            add_trace(
                "clarification_merged",
                "사용자 보충 답변을 원래 질문과 병합했습니다.",
                merge_status=merge_result["status"],
                merged_query=merge_result["merged_query"],
            )
            if merge_result[
                "status"
            ] == "NEEDS_CLARIFICATION" and not should_force_progress(document_id):
                clarifying_question = await _build_and_store_clarification(
                    document_id, pending["original_query"], history_window
                )
                add_trace(
                    "clarification_requested",
                    "보충 답변만으로는 부족하여 재질문을 다시 생성했습니다.",
                    clarifying_question=clarifying_question,
                )
                return persist_and_respond(
                    final_status="CLARIFICATION_REQUESTED",
                    answer=clarifying_question,
                    search_query=None,
                    sources=[],
                )

            search_query = merge_result["merged_query"]
            clear_pending_clarification(document_id)
            add_trace(
                "clarification_resolved",
                "재질문 상태를 종료하고 검색용 질문을 확정했습니다.",
                search_query=search_query,
            )
            logger.info("[Clarification Merge] %s → %s", user_query, search_query)
        else:
            initial_retrieval = await retrieve_chunks(document_id, user_query)
            embedded_question = initial_retrieval["embedding"]
            similar_chunks = initial_retrieval["chunks"]
            add_trace(
                "initial_retrieval",
                "원문 질문으로 먼저 검색해 추가 분류가 필요한지 확인했습니다.",
                search_query=user_query,
                retrieved_count=len(similar_chunks),
                top_similarity=(top_similarity(similar_chunks)),
            )

            if not history_window and has_any_results(similar_chunks):
                add_trace(
                    "standalone_fast_path",
                    "첫 질문에서 검색 결과가 충분해 분류를 생략하고 바로 답변 단계로 진행합니다.",
                    search_query=search_query,
                )
            else:
                query_status = await classify_query(document_id, user_query)
                add_trace(
                    "query_classified",
                    "질문 유형을 분류했습니다.",
                    classification=query_status,
                )

                if query_status == "OUT_OF_SCOPE":
                    add_trace(
                        "request_rejected",
                        "문서 범위를 벗어난 질문으로 판단해 종료했습니다.",
                    )
                    return persist_and_respond(
                        final_status="OUT_OF_SCOPE",
                        answer="이 질문은 업로드된 문서 범위를 벗어나 문서 기반으로 답변할 수 없습니다.",
                        search_query=None,
                        sources=[],
                    )

                elif query_status == "NEEDS_CLARIFICATION":
                    clarifying_question = await _build_and_store_clarification(
                        document_id, user_query, history_window
                    )
                    add_trace(
                        "clarification_requested",
                        "질문이 모호해 재질문을 생성했습니다.",
                        clarifying_question=clarifying_question,
                    )
                    return persist_and_respond(
                        final_status="CLARIFICATION_REQUESTED",
                        answer=clarifying_question,
                        search_query=None,
                        sources=[],
                    )

                elif query_status == "FOLLOW_UP":
                    rewrite_result = await rewrite_query_with_history(
                        document_id, user_query
                    )
                    add_trace(
                        "follow_up_rewritten",
                        "후속 질문을 독립형 질문으로 재작성했습니다.",
                        rewrite_status=rewrite_result["status"],
                        rewritten_query=rewrite_result["rewritten_query"],
                    )
                    if rewrite_result["status"] == "NEEDS_CLARIFICATION":
                        clarifying_question = await _build_and_store_clarification(
                            document_id, user_query, history_window
                        )
                        add_trace(
                            "clarification_requested",
                            "후속 질문 재작성에 실패해 재질문을 생성했습니다.",
                            clarifying_question=clarifying_question,
                        )
                        return persist_and_respond(
                            final_status="CLARIFICATION_REQUESTED",
                            answer=clarifying_question,
                            search_query=None,
                            sources=[],
                        )

                    search_query = rewrite_result["rewritten_query"]
                    if search_query != user_query:
                        logger.info(
                            "[Query Rewriting] %s → %s", user_query, search_query
                        )
                        embedded_question = None
                        similar_chunks = []
                else:
                    add_trace(
                        "standalone_query",
                        "독립형 질문으로 판단하여 원문 그대로 검색합니다.",
                        search_query=search_query,
                    )

        if embedded_question is None or search_query != user_query:
            retrieval_result = await retrieve_chunks(
                document_id, search_query, embedded_question
            )
            embedded_question = retrieval_result["embedding"]
            similar_chunks = retrieval_result["chunks"]
            add_trace(
                "query_embedded",
                "검색용 질문을 임베딩했습니다.",
                search_query=search_query,
            )
            add_trace(
                "chunks_retrieved",
                "유사 청크 검색을 수행했습니다.",
                retrieved_count=len(similar_chunks),
                top_similarity=(top_similarity(similar_chunks)),
            )
        else:
            add_trace(
                "retrieval_reused",
                "초기 검색 결과를 재사용해 추가 임베딩과 검색을 건너뛰었습니다.",
                search_query=search_query,
                retrieved_count=len(similar_chunks),
                top_similarity=(top_similarity(similar_chunks)),
            )

        if not has_any_results(similar_chunks):
            add_trace(
                "retrieval_failed",
                "임계값을 넘는 관련 청크를 찾지 못해 응답 생성을 중단했습니다.",
            )
            return persist_and_respond(
                final_status="NO_RESULT",
                answer="문서에서 관련 근거를 찾지 못했습니다.",
                search_query=search_query,
                sources=[],
            )

        if use_rerank:
            similar_chunks = rerank_chunks(search_query, similar_chunks)
            add_trace(
                "reranking_applied",
                f"Cross-Encoder로 재정렬 후 상위 {RERANKER_TOP_N}개 청크를 선택했습니다.",
                reranker_model=RERANKER_MODEL_NAME,
                top_n=RERANKER_TOP_N,
            )

        context = "\n\n".join(chunk["content"] for chunk in similar_chunks)
        answer = await generate_answer(context, search_query)
        add_trace(
            "answer_generated",
            "검색된 근거를 바탕으로 답변을 생성했습니다.",
        )

        append_history(document_id, user_query, answer)
        add_trace(
            "history_updated",
            "현재 질문과 답변을 대화 이력에 저장했습니다.",
            stored_query=user_query,
        )
        logger.debug("[Answer] %s", answer)

        response_sources = [
            {
                "content": chunk["content"],
                "similarity": chunk["similarity"],
            }
            for chunk in similar_chunks
        ]

        return persist_and_respond(
            final_status="ANSWERED",
            answer=answer,
            search_query=search_query,
            sources=response_sources,
        )
    except RAGException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        logger.error("질의응답 중 예기치 않은 오류: %s", str(e))
        raise HTTPException(
            status_code=500,
            detail="답변 생성 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
        ) from e


@app.post("/qa/reset")
async def reset_qa_session(body: DocumentIdBody):
    try:
        document_id = body.document_id
        conversation_history.pop(document_id, None)
        pending_clarifications.pop(document_id, None)
        logger.info("[세션 초기화] document_id=%s", document_id)
        return {
            "message": "질의 세션이 초기화되었습니다.",
            "document_id": document_id,
        }
    except Exception as e:
        logger.error("세션 초기화 중 오류: %s", str(e))
        raise HTTPException(
            status_code=500, detail="세션 초기화 중 오류가 발생했습니다."
        ) from e

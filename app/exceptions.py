"""
RAG 애플리케이션 예외 계층 및 Context Manager 예외 번역기
- 예외 클래스: 도메인 예외를 HTTP 관심사 없이 정의
- Context Manager: provider별 예외를 RAGException으로 번역 (비즈니스 로직 파일에서 except 블록 제거)
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator, Type

import requests

# ---------------------------------------------------------------------------
# 예외 클래스 계층
# ---------------------------------------------------------------------------


class RAGException(Exception):
    """모든 RAG 도메인 예외의 베이스. FastAPI HTTPException을 상속하지 않음."""

    status_code: int = 500

    def __init__(self, message: str, *, detail: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail


class EmbeddingError(RAGException):
    """임베딩 생성 실패 (Ollama / OpenAI)."""

    status_code = 503


class LLMError(RAGException):
    """LLM 호출 실패 (call_llm)."""

    status_code = 503


class DatabaseError(RAGException):
    """Supabase DB 연산 실패."""

    status_code = 503


class PDFProcessingError(RAGException):
    """PDF 추출 실패 (암호화 / 손상 / 이미지 전용)."""

    status_code = 422


class FileSystemError(RAGException):
    """파일시스템 오류 (디스크, 권한)."""

    status_code = 500


class RerankerError(RAGException):
    """CrossEncoder 모델 로딩 또는 예측 실패."""

    status_code = 503


# ---------------------------------------------------------------------------
# Context Manager — 예외 번역기
# ---------------------------------------------------------------------------

RAGExceptionType = Type[RAGException]


@contextmanager
def openai_error_context(
    timeout: int = 60, error_class: RAGExceptionType = LLMError
) -> Generator[None, None, None]:
    """OpenAI API 예외 → RAGException 번역.

    error_class 파라미터로 LLMError / EmbeddingError 를 선택해 재사용한다.
    """
    try:
        yield
    except RAGException:
        raise  # 이미 변환된 예외는 이중 래핑 방지
    except Exception as e:
        # openai는 선택적 의존성이므로 런타임에 import해서 타입 체크
        try:
            import openai as _openai  # noqa: PLC0415

            if isinstance(e, _openai.AuthenticationError):
                raise error_class(
                    "OpenAI API 키가 유효하지 않습니다.", detail=str(e)
                ) from e
            if isinstance(e, _openai.RateLimitError):
                raise error_class(
                    "OpenAI API 요청 한도를 초과했습니다. 잠시 후 다시 시도해주세요.",
                    detail=str(e),
                ) from e
            if isinstance(e, _openai.APIConnectionError):
                raise error_class(
                    "OpenAI API 서버에 연결할 수 없습니다.", detail=str(e)
                ) from e
            if isinstance(e, _openai.APITimeoutError):
                raise error_class(
                    f"OpenAI API 응답 시간이 초과되었습니다({timeout}초).",
                    detail=str(e),
                ) from e
            if isinstance(e, _openai.APIError):
                raise error_class(
                    "OpenAI API 오류가 발생했습니다.", detail=str(e)
                ) from e
        except ImportError:
            pass
        # openai 예외가 아닌 경우 일반 오류로 처리
        raise error_class(
            "OpenAI 요청 처리 중 오류가 발생했습니다.", detail=str(e)
        ) from e


@contextmanager
def ollama_error_context(
    timeout: int = 60, error_class: RAGExceptionType = LLMError
) -> Generator[None, None, None]:
    """requests(Ollama) 예외 → RAGException 번역.

    error_class 파라미터로 LLMError / EmbeddingError 를 선택해 재사용한다.
    """
    try:
        yield
    except RAGException:
        raise
    except requests.ConnectionError as e:
        raise error_class(
            "Ollama 서버에 연결할 수 없습니다. 서버가 실행 중인지 확인해주세요.",
            detail=str(e),
        ) from e
    except requests.Timeout as e:
        raise error_class(
            f"Ollama 서버 응답 시간이 초과되었습니다({timeout}초).", detail=str(e)
        ) from e
    except requests.HTTPError as e:
        status = e.response.status_code if e.response is not None else "unknown"
        body = e.response.text[:200] if e.response is not None else ""
        raise error_class(
            "Ollama 서버가 오류 응답을 반환했습니다.",
            detail=f"HTTP {status}: {body}",
        ) from e
    except requests.RequestException as e:
        raise error_class(
            "Ollama 서버 요청 중 오류가 발생했습니다.", detail=str(e)
        ) from e


@contextmanager
def supabase_error_context(
    error_class: RAGExceptionType = DatabaseError,
) -> Generator[None, None, None]:
    """Supabase/PostgREST 예외 → DatabaseError 번역.

    supabase==1.0.3에서 PostgREST 예외 타입이 버전마다 다르므로
    RAGException 여부만 확인하고 나머지는 일괄 catch한다.
    """
    try:
        yield
    except RAGException:
        raise
    except Exception as e:
        raise error_class("데이터베이스 오류가 발생했습니다.", detail=str(e)) from e


@contextmanager
def filesystem_error_context(
    error_class: RAGExceptionType = FileSystemError,
    *,
    fatal: bool = True,
) -> Generator[None, None, None]:
    """OSError → FileSystemError 번역.

    fatal=False 이면 OSError를 그대로 re-raise해 호출자가 로깅 후 무시할 수 있게 한다.
    """
    try:
        yield
    except RAGException:
        raise
    except OSError as e:
        if fatal:
            raise error_class("파일 시스템 오류가 발생했습니다.", detail=str(e)) from e
        raise  # non-fatal: 호출자가 except OSError로 받아서 로깅 후 계속

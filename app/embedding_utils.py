import asyncio
from typing import List

import aiohttp
import requests
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langsmith import traceable
from openai import AsyncOpenAI, OpenAI

from .config import (
    OLLAMA_BASE,
    OLLAMA_EMBED_MODEL,
    OPENAI_API_KEY,
    OPENAI_EMBEDDING_MODEL,
    PROVIDER,
)
from .exceptions import EmbeddingError, ollama_error_context, openai_error_context

_openai_client = None
_async_openai_client = None


def _get_openai_client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=OPENAI_API_KEY)
    return _openai_client


def _get_async_openai_client() -> AsyncOpenAI:
    global _async_openai_client
    if _async_openai_client is None:
        _async_openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    return _async_openai_client


def split_text(
    text: str, chunk_size: int = 1000, chunk_overlap: int = 100
) -> List[str]:
    """
    [TODO Day 1] 긴 텍스트를 적절한 크기의 청크로 분할하는 함수를 구현하세요.

    요구사항:
    1. 텍스트를 의미 단위로 분할할 수 있는 방법을 직접 조사하여 구현하세요.
       - 어떤 라이브러리를 사용할지, 어떤 방식으로 분할할지는 스스로 결정하세요.
    2. chunk_size와 chunk_overlap 파라미터가 실제 분할 결과에 어떤 영향을 미치는지
       이해한 상태에서 구현하세요.

    3. (Deep Dive) 다양한 chunk_size를 실험해보고 최적의 값을 찾아보세요.
       힌트: REFERENCE.md의 청킹 섹션을 먼저 읽고,
       어떤 파라미터가 품질에 영향을 주는지 파악하세요.

    Args:
        text (str): 분할할 전체 텍스트
        chunk_size (int): 청크 당 최대 크기
        chunk_overlap (int): 청크 간 중복 크기

    Returns:
        List[str]: 분할된 텍스트 청크 리스트
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", "? ", "! ", "다. ", " "],
        length_function=len,
    )
    return splitter.split_text(text)


@traceable(run_type="embedding", name="get_embedding")
async def get_embedding(text: str) -> List[float]:
    """
    [TODO Day 2] 텍스트의 벡터 임베딩을 생성하는 함수를 구현하세요.

    요구사항:
    1. 로컬에서 실행 중인 Ollama 서버를 통해 임베딩 벡터를 생성하세요.
       - Ollama API 스펙을 직접 조사하세요: https://github.com/ollama/ollama/blob/main/docs/api.md
       - 사용할 모델과 반환 벡터 차원은 README.md의 환경 설정 섹션을 참고하세요.
    2. 반환값은 float 숫자로 구성된 리스트여야 합니다.
    3. Ollama 서버가 응답하지 않는 경우를 적절히 처리하세요.

    (선택사항) OpenAI 사용:
    - .env에서 PROVIDER=openai로 설정한 경우에만 사용됩니다.
    - OpenAI Embeddings API 스펙을 직접 조사하세요.

    Args:
        text (str): 임베딩할 텍스트

    Returns:
        List[float]: 임베딩 벡터
    """
    if PROVIDER == "openai":
        with openai_error_context(timeout=30, error_class=EmbeddingError):
            client = _get_async_openai_client()
            response = await client.embeddings.create(
                model=OPENAI_EMBEDDING_MODEL, input=text
            )
            return response.data[0].embedding

    def _sync_ollama():
        with ollama_error_context(timeout=30, error_class=EmbeddingError):
            response = requests.post(
                f"{OLLAMA_BASE}/api/embed",
                json={"model": OLLAMA_EMBED_MODEL, "input": text},
                timeout=30,
            )
            response.raise_for_status()
            embeddings = response.json().get("embeddings")
            if not embeddings:
                raise EmbeddingError("임베딩 서버에서 빈 응답을 반환했습니다.")
            return embeddings[0]

    return await asyncio.to_thread(_sync_ollama)


async def get_embedding_async(session: aiohttp.ClientSession, text: str) -> List[float]:
    try:
        async with session.post(
            f"{OLLAMA_BASE}/api/embed",
            json={"model": OLLAMA_EMBED_MODEL, "input": text},
        ) as response:
            if response.status != 200:
                raise EmbeddingError(
                    "임베딩 서버가 오류 응답을 반환했습니다.",
                    detail=f"HTTP {response.status}",
                )
            result = await response.json()
            embeddings = result.get("embeddings")
            if not embeddings:
                raise EmbeddingError("임베딩 서버에서 빈 응답을 반환했습니다.")
            return embeddings[0]
    except EmbeddingError:
        raise
    except aiohttp.ClientConnectionError as e:
        raise EmbeddingError(
            "임베딩 서버(Ollama)에 연결할 수 없습니다.", detail=str(e)
        ) from e
    except aiohttp.ServerTimeoutError as e:
        raise EmbeddingError(
            "임베딩 서버 응답 시간이 초과되었습니다.", detail=str(e)
        ) from e
    except Exception as e:
        raise EmbeddingError(
            "임베딩 요청 처리 중 오류가 발생했습니다.", detail=str(e)
        ) from e


async def get_embeddings_batch(chunks: List[str]) -> List[List[float]]:
    async with aiohttp.ClientSession() as session:
        tasks = [get_embedding_async(session, chunk) for chunk in chunks]
        return await asyncio.gather(*tasks)


@traceable(run_type="embedding", name="get_embeddings_batch")
async def get_embeddings_batch_ollama(chunks: List[str]) -> List[List[float]]:
    if PROVIDER == "openai":
        with openai_error_context(timeout=60, error_class=EmbeddingError):
            client = _get_async_openai_client()
            response = await client.embeddings.create(
                model=OPENAI_EMBEDDING_MODEL, input=chunks
            )
            return [item.embedding for item in response.data]

    def _sync_ollama():
        with ollama_error_context(timeout=60, error_class=EmbeddingError):
            response = requests.post(
                f"{OLLAMA_BASE}/api/embed",
                json={"model": OLLAMA_EMBED_MODEL, "input": chunks},
                timeout=60,
            )
            response.raise_for_status()
            embeddings = response.json().get("embeddings")
            if not embeddings:
                raise EmbeddingError("임베딩 서버에서 빈 배치 응답을 반환했습니다.")
            return embeddings

    return await asyncio.to_thread(_sync_ollama)

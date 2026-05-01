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
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", "? ", "! ", "다. ", " "],
        length_function=len,
    )
    return splitter.split_text(text)


@traceable(run_type="embedding", name="get_embedding")
async def get_embedding(text: str) -> List[float]:

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

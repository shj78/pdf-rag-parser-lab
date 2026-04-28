import os
from typing import Any, Dict, List

from supabase import Client, create_client

from .exceptions import DatabaseError, supabase_error_context

# 환경 변수 로드 및 Supabase 클라이언트 초기화
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL과 SUPABASE_KEY가 설정되어 있어야 합니다.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def save_embedding(
    document_id: str, chunk: str, embedding: List[float], chunk_index: int
) -> Dict:
    """
    [TODO Day 2] 문서 청크와 임베딩 벡터를 Supabase DB에 저장하는 함수입니다.

    요구사항:
    1. README.md의 데이터베이스 구성 섹션에서 생성한 테이블에 데이터를 저장하세요.
       - 어떤 컬럼에 어떤 값을 저장해야 하는지 SQL 스키마를 직접 확인하세요.
    2. Supabase Python 클라이언트 사용 방법은 직접 조사하세요.
       - 힌트: 위에서 이미 초기화된 `supabase` 클라이언트를 활용하세요.

    Args:
        document_id (str): 문서 ID
        chunk (str): 텍스트 청크 내용
        embedding (List[float]): 임베딩 벡터
        chunk_index (int): 청크 순서 인덱스

    Returns:
        Dict: 저장된 데이터 정보
    """
    # ---------------------------------------------------------
    # [Day 2] 과제: 여기에 DB 저장 로직을 작성하세요.
    # ---------------------------------------------------------
    with supabase_error_context():
        result = (
            supabase.table("document_chunks")
            .insert(
                {
                    "document_id": document_id,
                    "content": chunk,
                    "embedding": embedding,
                    "chunk_index": chunk_index,
                }
            )
            .execute()
        )
        if not result.data:
            raise DatabaseError("청크 저장 후 데이터베이스에서 빈 응답을 받았습니다.")
        return result.data[0]


def search_similar_embeddings(
    query_embedding: List[float],
    document_id: str,
    limit: int = 5,
    similarity_threshold: float = 0.7,
) -> List[Dict[str, Any]]:
    """
    [TODO Day 3] 사용자의 질문 벡터와 유사한 문서 청크를 검색하는 함수입니다.

    요구사항:
    1. README.md의 데이터베이스 구성 섹션에서 생성한 RPC 함수를 활용하여 유사도 검색을 수행하세요.
       - 어떤 인자를 전달해야 하는지 SQL 스키마의 RPC 함수 정의를 직접 확인하세요.
    2. 유사도(similarity)가 similarity_threshold 이상인 결과만 필터링하세요. (선택사항)

    Args:
        query_embedding (List[float]): 질문의 임베딩 벡터
        document_id (str): 검색할 문서 ID
        limit (int): 반환할 최대 결과 수
        similarity_threshold (float): 유사도 임계값

    Returns:
        List[Dict[str, Any]]: 유사한 문서 청크 리스트
    """
    # ---------------------------------------------------------
    # [Day 3] 과제: 여기에 벡터 검색 로직을 작성하세요.
    # ---------------------------------------------------------
    with supabase_error_context():
        response = supabase.rpc(
            "match_documents",
            {
                "query_embedding": query_embedding,
                "match_count": limit,
                "p_document_id": document_id,
            },
        ).execute()
        results = response.data or []
        return [
            result for result in results if result["similarity"] >= similarity_threshold
        ]

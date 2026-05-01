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

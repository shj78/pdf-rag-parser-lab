"""
Locust 스트레스 테스트

사용법:
  1. pip install locust
  2. 서버 실행: uvicorn app.main:app --host 0.0.0.0 --port 8000
  3. PDF 업로드 후 발급된 document_id를 DOCUMENT_ID에 입력
  4. locust --host http://localhost:8000
  5. 브라우저에서 http://localhost:8089 접속
"""

import os

from locust import HttpUser, between, task

# 테스트할 document_id — PDF 업로드 후 발급된 값으로 교체
DOCUMENT_ID = os.getenv("TEST_DOCUMENT_ID", "82c612c8-467e-43c2-b285-76b446d112b4")

SAMPLE_QUERIES = [
    "이 문서의 주요 내용은 무엇인가요?",
    "핵심 목표를 요약해주세요.",
    "지원 대상은 누구인가요?",
    "신청 방법을 알려주세요.",
    "일정은 어떻게 되나요?",
]


class RAGUser(HttpUser):
    """일반 사용자 시나리오 — QA 위주"""

    wait_time = between(1, 3)  # 요청 간 대기 1~3초

    @task(5)
    def ask_question(self):
        """QA 요청 (가장 빈번한 작업)"""
        import random

        self.client.post(
            "/qa",
            json={
                "document_id": DOCUMENT_ID,
                "query": random.choice(SAMPLE_QUERIES),
                "use_rerank": False,
            },
            name="/qa",
        )

    @task(2)
    def ask_question_with_rerank(self):
        """리랭킹 포함 QA 요청"""
        import random

        self.client.post(
            "/qa",
            json={
                "document_id": DOCUMENT_ID,
                "query": random.choice(SAMPLE_QUERIES),
                "use_rerank": True,
            },
            name="/qa (rerank)",
        )

    @task(3)
    def health_check(self):
        """헬스체크"""
        self.client.get("/health", name="/health")

    @task(1)
    def reset_session(self):
        """세션 초기화"""
        self.client.post(
            "/qa/reset",
            json={"document_id": DOCUMENT_ID},
            name="/qa/reset",
        )


class UploadUser(HttpUser):
    """PDF 업로드 시나리오 — 업로드 부하 테스트"""

    wait_time = between(5, 10)  # 업로드는 간격 길게

    # 테스트용 PDF 경로 — 실제 파일로 교체
    PDF_PATH = (
        "app/uploads/(붙임2) 2025년 데이터센터 산업 활성화 지원 사업 통합_안내서.pdf"
    )

    @task
    def upload_document(self):
        if not os.path.exists(self.PDF_PATH):
            return
        with open(self.PDF_PATH, "rb") as f:
            self.client.post(
                "/documents/",
                files={"file": ("test.pdf", f, "application/pdf")},
                name="/documents/",
            )

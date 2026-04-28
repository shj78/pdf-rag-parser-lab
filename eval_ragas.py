"""
RAGAS 기반 RAG 에이전트 평가 스크립트

평가 메트릭:
  - Faithfulness       : 답변이 검색된 컨텍스트에 얼마나 충실한지
  - Answer Relevancy   : 답변이 질문에 얼마나 관련 있는지
  - Context Precision  : 검색된 청크 중 관련 청크가 상위에 위치하는지
  - Context Recall     : 정답에 필요한 정보가 검색된 청크에 포함되는지

실행 방법:
  python eval_ragas.py --doc-id <document_id>
  python eval_ragas.py  # 기본 DOC_ID 사용
"""

import argparse
import logging
import re
import sys
import time

import requests
from datasets import Dataset
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from ragas import RunConfig, evaluate
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms.base import (
    LangchainLLMWrapper,  # DeprecationHelper 우회, 실제 클래스 직접 사용
)
from ragas.metrics import (  # 인스턴스로 임포트 (collections는 모듈 반환으로 사용 불가)
    answer_relevancy,
    context_precision,
    faithfulness,
)

# ──────────────────────────────────────────────
# 설정
# ──────────────────────────────────────────────
BASE_URL = "http://localhost:8000"
DEFAULT_DOC_ID = "86cff8ff-0a23-4913-acf7-83b2e456abce"

OPENAI_CHAT_MODEL = "gpt-4o-mini"
OPENAI_EMBED_MODEL = "text-embedding-3-small"

# ──────────────────────────────────────────────
# 로거 설정
# ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# RAGAS 내부 디버그 로그 활성화
logging.getLogger("ragas").setLevel(logging.DEBUG)
logging.getLogger("ragas.metrics").setLevel(logging.DEBUG)
logging.getLogger("ragas.llms").setLevel(logging.DEBUG)

# ──────────────────────────────────────────────
# 테스트셋 (테스트셋.txt 기반)
# 각 항목: (카테고리, 질문, 정답, 선행_질문_or_None)
# ──────────────────────────────────────────────
TEST_CASES = [
    # ── 카테고리 1: 수치/사실 확인 (단답형, 문서에 숫자·명칭이 직접 명시) ──
    (
        "수치_사실확인",
        "보건의료 빅데이터 시범사업의 추진 기간은 언제부터 언제까지인가요?",
        "시범사업은 2018년부터 2020년까지 추진됩니다.",
        None,
    ),
    # ── 카테고리 2: 목록/열거형 (문서에 리스트로 명시된 항목) ──────────
    (
        "목록_열거형",
        "보건의료 빅데이터 거버넌스에서 운영하는 3개 분과위원회의 명칭은 무엇인가요?",
        "데이터 연계 분과위원회, 데이터제공 심의 분과위원회, 개인정보보호 분과위원회입니다.",
        None,
    ),
    # ── 카테고리 3: 절차/프로세스 (단계가 문서에 명시된 순서형) ─────────
    (
        "절차_프로세스",
        "보건의료 빅데이터 플랫폼에서 데이터 이용을 신청하는 절차는 어떻게 되나요?",
        "자료이용 신청 접수 후 이용목적 등을 살펴 자료 제공여부를 건별로 심의합니다.",
        None,
    ),
    # ── 카테고리 4: 개념/기술 설명 (특정 기술·방식의 정의가 문서에 명시) ─
    (
        "개념_기술설명",
        "분석자료 공유·활용 네트워크에서 개인정보를 보호하는 방식은 무엇인가요?",
        "각 병원이 보유한 의료기록(EMR) 데이터에서 개인정보를 이동시키지 않고, 통계처리·분석한 결과만을 취합하여 제공합니다.",
        None,
    ),
    # ── 카테고리 5: 이용자/허용 범위 (이용 자격·허용·제한 조건이 명시) ──
    (
        "이용자_허용범위",
        "보건의료기술 연구 분야에서 제외되는 연구 유형은 무엇인가요?",
        "시장분석, 개발된 제품의 마케팅 등 의학적 진보와 무관한 영리적 연구는 제외됩니다.",
        None,
    ),
]


# ──────────────────────────────────────────────
# RAGAS용 answer 정제
# ──────────────────────────────────────────────
def clean_answer_for_ragas(text: str) -> str:
    """마크다운·인용마커·섹션헤더를 제거해 RAGAS에 적합한 평문으로 만든다."""
    text = re.sub(r"\[\d+\]", "", text)  # [1], [2] 인용 마커 제거
    text = re.sub(
        r"\n(근거|한계|참고|출처)\s*:.*", "", text, flags=re.DOTALL
    )  # 섹션 이후 제거
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)  # **bold** → 일반 텍스트
    text = re.sub(r"\*(.+?)\*", r"\1", text)  # *italic* → 일반 텍스트
    text = re.sub(r"^\s*\*+\s*", "", text, flags=re.MULTILINE)  # * bullet 제거
    text = re.sub(r"^\s*#+\s*", "", text, flags=re.MULTILINE)  # ## 헤더 제거
    text = re.sub(r"\n{2,}", "\n", text)  # 빈 줄 정리
    return text.strip()


# ──────────────────────────────────────────────
# RAG API 호출
# ──────────────────────────────────────────────
def reset_session(doc_id: str) -> None:
    """테스트 케이스 간 대화 히스토리를 초기화한다."""
    resp = requests.post(
        f"{BASE_URL}/qa/reset",
        json={"document_id": doc_id},
        timeout=10,
    )
    resp.raise_for_status()


def call_rag_api(
    doc_id: str, query: str, use_rerank: bool = False, timeout: int = 90
) -> dict:
    """RAG /qa 엔드포인트를 호출하고 answer, sources를 반환한다."""
    resp = requests.post(
        f"{BASE_URL}/qa",
        json={"document_id": doc_id, "query": query, "use_rerank": use_rerank},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()


# ──────────────────────────────────────────────
# 로그 출력 헬퍼
# ──────────────────────────────────────────────
def log_case(
    idx: int,
    category: str,
    question: str,
    ground_truth: str,
    answer: str,
    sources: list,
    scores: dict,
) -> None:
    sep = "═" * 70
    logger.info(sep)
    logger.info(f"[#{idx}] 카테고리: {category}")
    logger.info(f"질문    : {question}")
    logger.info(f"정답    : {ground_truth}")
    logger.info(f"RAG 답변: {answer}")
    logger.info("검색된 청크:")
    if sources:
        for i, src in enumerate(sources):
            preview = src["content"].replace("\n", " ")[:120]
            logger.info(f"  [{i}] (similarity={src['similarity']:.4f}) {preview}...")
    else:
        logger.info("  (검색된 청크 없음)")
    logger.info("평가 지표:")
    logger.info(f"  Faithfulness     : {scores.get('faithfulness', 'N/A')}")
    logger.info(f"  Answer Relevancy : {scores.get('answer_relevancy', 'N/A')}")
    logger.info(f"  Context Precision: {scores.get('context_precision', 'N/A')}")


def log_summary(all_scores: list[dict]) -> None:
    sep = "═" * 70
    metrics = [
        "faithfulness",
        "answer_relevancy",
        "context_precision",
    ]
    logger.info("\n" + sep)
    logger.info("[RAGAS 평가 최종 집계]")
    logger.info(f"  총 케이스 수: {len(all_scores)}개")
    for metric in metrics:
        vals = [s[metric] for s in all_scores if isinstance(s.get(metric), float)]
        avg = sum(vals) / len(vals) if vals else float("nan")
        label = {
            "faithfulness": "Faithfulness     ",
            "answer_relevancy": "Answer Relevancy ",
            "context_precision": "Context Precision",
        }[metric]
        logger.info(f"  {label}: {avg:.4f}  (유효 샘플={len(vals)})")
    logger.info(sep)


# ──────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────
def main(doc_id: str, only_case: int | None = None, use_rerank: bool = False) -> None:
    # RAGAS에서 사용할 OpenAI LLM / Embedding 설정
    from dotenv import load_dotenv

    load_dotenv()
    import os

    api_key = os.getenv("OPENAI_API_KEY")

    selected_llm = LangchainLLMWrapper(
        ChatOpenAI(model=OPENAI_CHAT_MODEL, temperature=0, api_key=api_key),
    )
    selected_embeddings = LangchainEmbeddingsWrapper(
        OpenAIEmbeddings(model=OPENAI_EMBED_MODEL, api_key=api_key)
    )

    # 각 메트릭에 LLM/Embedding 주입
    metrics = [faithfulness, answer_relevancy, context_precision]
    for metric in metrics:
        metric.llm = selected_llm
        if hasattr(metric, "embeddings"):
            metric.embeddings = selected_embeddings

    collected = []  # RAGAS Dataset 구성용
    raw_cases = []  # 로그 출력용 (question, ground_truth, answer, sources)

    cases = (
        [(only_case, TEST_CASES[only_case - 1])]
        if only_case
        else list(enumerate(TEST_CASES, 1))
    )

    mode_label = (
        "Reranking ON (bge-reranker-v2-m3)"
        if use_rerank
        else "Reranking OFF (baseline)"
    )
    logger.info(f"\nRAGAS 평가 시작 — document_id: {doc_id}")
    logger.info(f"모드: {mode_label}")
    logger.info(f"총 {len(cases)}개 케이스\n")

    for idx, (category, question, ground_truth, prior_question) in cases:
        logger.info(f"[#{idx}/{len(TEST_CASES)}] 질문 호출 중: {question[:60]}...")
        start = time.perf_counter()

        try:
            reset_session(doc_id)
            # 후속 질문인 경우 선행 질문을 먼저 전송해 대화 맥락 형성
            if prior_question:
                call_rag_api(doc_id, prior_question, use_rerank=use_rerank)

            data = call_rag_api(doc_id, question, use_rerank=use_rerank)
            elapsed = int((time.perf_counter() - start) * 1000)

            answer = data.get("answer", "")
            sources = data.get("sources", [])
            contexts = [src["content"] for src in sources] if sources else []

            entry = {
                "user_input": question,
                "response": clean_answer_for_ragas(answer),  # 인용마커·섹션 제거
                "reference": ground_truth,
                "retrieved_contexts": contexts,
            }
            collected.append(entry)
            raw_cases.append(
                {
                    "category": category,
                    "question": question,
                    "ground_truth": ground_truth,
                    "answer": answer,
                    "sources": sources,
                }
            )
            logger.info(f"  → 완료 ({elapsed}ms)")

        except Exception as e:
            logger.error(f"  → 오류 발생: {e}")
            # 오류 케이스도 빈 값으로 포함
            collected.append(
                {
                    "user_input": question,
                    "response": f"[오류: {e}]",
                    "reference": ground_truth,
                }
            )
            raw_cases.append(
                {
                    "category": category,
                    "question": question,
                    "ground_truth": ground_truth,
                    "answer": f"[오류: {e}]",
                    "sources": [],
                }
            )

    # ── RAGAS 평가 실행 ───────────────────────────────────────────────
    logger.info("\nRAGAS 평가 실행 중...\n")
    dataset = Dataset.from_list(collected)

    result = evaluate(
        dataset=dataset,
        metrics=metrics,
        llm=selected_llm,
        embeddings=selected_embeddings,
        raise_exceptions=False,
        run_config=RunConfig(
            timeout=300,
            max_retries=15,
            max_wait=120,
            max_workers=2,
            log_tenacity=True,
        ),
    )

    result_df = result.to_pandas()

    # ── 케이스별 로그 출력 ────────────────────────────────────────────
    all_scores = []
    for i, case in enumerate(raw_cases):
        row = result_df.iloc[i]
        scores = {
            "faithfulness": row.get("faithfulness"),
            "answer_relevancy": row.get("answer_relevancy"),
            "context_precision": row.get("context_precision"),
        }
        # None/NaN을 float로 변환
        for k, v in scores.items():
            try:
                scores[k] = float(v)
            except (TypeError, ValueError):
                scores[k] = "N/A"

        log_case(
            idx=i + 1,
            category=case["category"],
            question=case["question"],
            ground_truth=case["ground_truth"],
            answer=case["answer"],
            sources=case["sources"],
            scores=scores,
        )
        all_scores.append(scores)

    # ── 최종 집계 ─────────────────────────────────────────────────────
    log_summary(all_scores)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RAGAS RAG 평가 스크립트")
    parser.add_argument(
        "--doc-id",
        default=DEFAULT_DOC_ID,
        help="평가할 문서의 document_id (기본값: eval_experiment1.py의 DOC_ID)",
    )
    parser.add_argument(
        "--case",
        type=int,
        default=None,
        help="특정 케이스 번호만 실행 (1-based, 미지정 시 전체 실행)",
    )
    parser.add_argument(
        "--rerank",
        action="store_true",
        default=False,
        help="Cross-Encoder reranking 적용 (BAAI/bge-reranker-v2-m3)",
    )
    args = parser.parse_args()
    main(args.doc_id, args.case, args.rerank)

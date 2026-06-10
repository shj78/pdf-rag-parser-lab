# PDF RAG Parser Lab

`pdf-rag-parser-lab`은 PDF 파서 비교, 청킹(chunking) 및 검색(retrieval) 전략 테스트, 기존 리랭커(reranker) 통합, 그리고 NDCG 지향 메트릭을 통한 실행 평가를 위한 실험용 저장소입니다.

현재 단계에서는 parser comparison MVP, `ParsedDocument` 기반 fixed-size chunking, 로컬 lexical/embedding in-memory retrieval, 기존 리랭커 브릿지, NDCG 기반 retrieval evaluation CLI, 그리고 Streamlit PDF 질문 데모가 구현되어 있습니다.

## 포트폴리오 포인트

이 프로젝트는 단순 PDF QA 데모가 아니라, **PDF 파싱 품질이 RAG 검색 품질에 미치는 영향**을 분리해서 측정하는 실험 워크벤치입니다.

- 텍스트 레이어가 없거나 표/달력 중심인 PDF에서 `pdfplumber`, `PyMuPDF`, `MinerU`, `OpenDataLoader`를 동일한 `ParsedDocument` 스키마로 정규화합니다.
- 표가 별도 chunk로 분리될 때 월/섹션 문맥이 사라지는 문제를 발견하고, table chunk context 옵션으로 검색 랭킹을 개선했습니다.
- 검색 품질은 감이 아니라 manual relevance label과 `NDCG@k`로 측정합니다.
- Streamlit UI는 공개 데모용 PDF 업로드/질문 흐름에 집중하고, 검색 품질 평가는 README와 CLI artifact로 재현 가능하게 남깁니다.
- 기존 production reranker를 새로 만들지 않고 `python_module` bridge로 연결해 실험 파이프라인에 붙일 수 있게 했습니다.

대표 full-PDF 실험에서는 `2026 서울시 청년수당 참여자 안내책자` 8개 질문과 26개 수동 relevance label을 기준으로 MinerU parser artifact, table-aware fixed chunking, lexical retrieval 조합을 평가했습니다. Lexical baseline은 `NDCG@1 = 0.250`, `NDCG@10 = 0.554`로 정답 근거를 top-10 안에서는 찾지만 1위로 올리는 랭킹 품질에 한계가 있었습니다. 기존 CrossEncoder reranker(`BAAI/bge-reranker-v2-m3`)를 bridge로 연결하자 `NDCG@1 = 0.708`, `NDCG@10 = 0.800`까지 개선되었습니다.

## 이 저장소의 존재 이유

기존의 PDF RAG 시스템에서는 표 파싱의 베이스라인(baseline)으로 `pdfplumber`를 사용해 왔습니다. 초기 실험에는 도움이 되었으나, 다음 단계의 실험을 진행하기에는 표 추출의 정확도와 구조 보존 능력이 충분히 강력하지 않았습니다.

이 랩(Lab) 저장소는 다음과 같은 핵심 관심사를 분리하기 위해 존재합니다:

- `pdfplumber`를 베이스라인 파서로 명시적으로 다룸
- 베이스라인과 대안 파서들을 비교
- 파서, 청킹, 검색, 리랭커 통합 및 평가 책임을 명확히 분리
- 리랭킹 후의 다운스트림 검색 영향도를 쉽게 측정
- 재사용 가능한 실험 레이아웃으로 NDCG 기반 평가 준비

## 현재 범위 (Current Scope)

현재 구현 범위는 다음과 같습니다:

- 저장소 구조 정의
- 공통 스키마 및 설정(configuration) 로더
- parser comparison CLI 및 실행 러너
- `pdfplumber` baseline parser 어댑터
- `pymupdf` parser 어댑터
- `mineru` parser 어댑터
- `opendataloader` parser 어댑터
- fixed-size chunker
- table chunk에 page/month context를 붙이는 실험 옵션
- 로컬 lexical in-memory 검색 index
- hashing embedding 기반 in-memory 검색 index
- Retriever 오케스트레이션 및 기존 python module 리랭커 브릿지
- NDCG@k 기반 retrieval evaluator 및 `retrieval-eval` CLI
- Streamlit 기반 PDF 업로드/질문 데모
- `OPENAI_API_KEY` 또는 `OLLAMA_BASE`가 있을 때 근거 기반 QA 답변 생성
- parsed document / comparison artifact 저장

이번 단계의 범위 밖(Out of scope) 사항:

- production semantic embedding provider 연결
- 새 리랭커 모델 구현
- UI에서의 reranker 비교 실행/전환
- heading-aware chunking 및 부모-자식 검색

## 베이스라인 vs 대안 파서

- `pdfplumber`: 베이스라인 파서. 기존 시스템에서 이미 시도되었으며 표 충실도와 구조 보존의 한계를 보여주었기 때문에 참조 포인트로 사용됩니다.
- `pymupdf`: 비교를 위한 대안 파서 후보.
- `mineru`: 내장 OCR 기반. 텍스트 레이어가 없는 안내책자형 PDF 처리. 무거운 ML 스택을 끌고 와서 **격리 venv `.venv-mineru/`** 에 별도 설치 (아래 섹션 참조).
- `opendataloader`: Java 기반 local 추출 + 선택적 hybrid OCR. **격리 venv `.venv-opendataloader/`** 에 별도 설치하며, hybrid 모드는 별도 backend 서버가 필요합니다.

목표는 단순히 파서 수준의 비교만이 아닙니다. 이 랩은 파서의 출력이 나중에 청킹, 검색, 리랭킹 및 NDCG 기반 평가로 흐를 수 있도록 설계되었습니다.

## 저장소 구조

```text
pdf-rag-parser-lab/
  apps/
    parser-lab-ui/
      app.py
      README.md
      components/
      views/
  src/
    __init__.py
    cli.py
    schemas.py
    parsers/
    chunkers/
    retrieval/
    evaluation/
    metadata/
  experiments/
    parser_comparison/
    retrieval_eval/
  data/
    eval/
    README.md
  config.example.yaml
  pyproject.toml
  requirements.txt
  .env.example
  .gitignore
```

## 모듈별 책임 (Module Responsibilities)

| 영역 | 책임 | 아직 구현되지 않은 기능 |
| --- | --- | --- |
| `src/parsers` | 파서 인터페이스, 파서 기술자(descriptor), 파서 팩토리 | 비교 품질 개선 및 parser별 옵션 확장 |
| `src/chunkers` | 청커 인터페이스 및 청크 메타데이터 계약 | heading-aware chunking, 부모-자식 chunking |
| `src/retrieval` | lexical/embedding in-memory index, Retriever, 기존 리랭커 브릿지 | production embedding provider, 추가 reranker mode |
| `src/evaluation` | 관련성 라벨, NDCG@k, query/run 평가기 | 추가 메트릭 |
| `src/metadata` | 필터링 및 다운스트림 분석을 위한 메타데이터 계약 | 공통 메타데이터 생성/정규화 helper |
| `experiments/parser_comparison` | 파서 비교 실행 및 artifact 생성 | 동작 가능 |
| `experiments/retrieval_eval` | parsed artifact 기반 retrieval/NDCG 실행 | 동작 가능 |
| `apps/parser-lab-ui` | PDF 업로드/질문, 근거 검색, 답변 생성 데모 | UI reranker 비교 전환 |

## 빠른 시작 (Quick Start)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

parser comparison 예시 실행:

```bash
python -m src.cli parser-compare \
  --config config.example.yaml \
  --documents /path/to/pdfs
```

Streamlit UI 실행:

```bash
pipenv run streamlit run apps/parser-lab-ui/app.py
```

UI에서는 PDF 업로드 후 파서 선택, chunk 생성, 검색/답변 생성을 시험할 수 있습니다. 검색 품질 평가는 UI에 노출하지 않고, 아래 `Retrieval Evaluation` 섹션의 CLI와 저장 artifact로 재현합니다.

테스트 및 린트:

```bash
pipenv run pytest tests -q
pipenv run ruff check .
```

## Retrieval Evaluation

`retrieval-eval`은 parsed document artifact, query JSONL, relevance label JSONL을 입력으로 받아 chunking, retrieval, optional reranking, NDCG 평가를 한 번에 실행합니다.

```bash
pipenv run python -m src.cli retrieval-eval \
  --config experiments/retrieval_eval/config.2026_youth_allowance_pages1_3.yaml
```

평가용 query/label 형식:

```json
{"query_id":"t1_apr_payment_2","query_text":"4월 달력에서 지급②는 몇 일에 표시되어 있나요?"}
{"query_id":"t1_apr_payment_2","chunk_id":"2026-1차 참여자 안내책자:mineru:p2:table:2","grade":2}
```

생성 결과는 `artifacts/retrieval-eval-runs/` 아래에 저장되며 git에는 포함하지 않습니다.

### 대표 검색 품질 평가 결과

공개 포트폴리오용 핵심 결과는 Streamlit UI가 아니라 CLI 평가 결과로 정리합니다. 이 평가는 LLM 답변 품질이 아니라 **질문에 답하는 근거 chunk가 검색 결과 상위에 배치되는지**를 측정합니다.

Full PDF baseline:

```bash
pipenv run python -m src.cli retrieval-eval \
  --config experiments/retrieval_eval/config.2026_youth_allowance_full_mineru.yaml
```

Full PDF reranker run:

```bash
pipenv run python -m src.cli retrieval-eval \
  --config experiments/retrieval_eval/config.2026_youth_allowance_full_mineru_reranker.yaml
```

| 항목 | 값 |
| --- | ---: |
| 기준 문서 | `2026 서울시 청년수당 참여자 안내책자` |
| 파서 | MinerU OCR |
| 평가 질문 | 8 |
| 수동 relevance label | 26 |
| 검색 대상 chunk | 89 |
| baseline 검색 방식 | lexical in-memory |
| reranker | `app.main:rerank_chunks` / `BAAI/bge-reranker-v2-m3` |
| 검색 후보 | top-10 |

| 지표 | lexical baseline | + reranker | 개선폭 |
| --- | ---: | ---: | ---: |
| `NDCG@1` | 0.250 | 0.708 | +0.458 |
| `NDCG@3` | 0.363 | 0.753 | +0.390 |
| `NDCG@5` | 0.418 | 0.785 | +0.367 |
| `NDCG@10` | 0.554 | 0.800 | +0.245 |

이 결과는 lexical baseline이 근거를 완전히 놓치는 문제보다는 **정답 근거를 1위로 올리지 못하는 랭킹 문제**가 컸고, CrossEncoder reranker가 이 병목을 상당 부분 개선했음을 보여줍니다. 다음 실험은 embedding retrieval, lexical+embedding hybrid, query type별 실패 분석 순으로 비교하는 방향이 적합합니다.

참고로 1~3페이지 smoke 실험에서는 달력/지급일 질의 6개에 대해 table context chunking을 적용했을 때 `NDCG@1/3/5 = 1.0`을 확인했습니다. 이 결과는 regression smoke 성격이며, 위 full PDF baseline과 직접 비교하지 않습니다.

### NotebookLM으로 라벨 후보 만들기

NotebookLM은 평가 질문과 예상 답변 후보를 빠르게 뽑는 용도로 쓰기 좋습니다. 다만 `NDCG@k` 라벨은 최종적으로 이 저장소의 chunk ID에 매핑되어야 하므로, NotebookLM 결과를 그대로 정답 라벨로 쓰지는 않습니다.

권장 절차:

1. 기준 PDF를 NotebookLM에 넣고 페이지/표/날짜/금액처럼 문서 근거가 명확한 질문을 뽑습니다.
2. `data/eval/*_queries.jsonl`에는 `query_id`, `query_text`, `metadata.answer_hint`, `metadata.page_range`, `metadata.needs_pdf_verification`을 기록합니다.
3. parser comparison 또는 PDF RAG UI로 같은 PDF를 파싱하고 chunk 미리보기에서 정답 근거 chunk를 확인합니다.
4. `data/eval/*_relevance.jsonl`에는 `query_id`, `chunk_id`, `grade`, `rationale`, `source`를 기록합니다.
5. `grade=2`는 질문에 직접 답하는 근거, `grade=1`은 부분 근거, `grade=0`은 혼동되기 쉬운 hard negative에 사용합니다.

라벨의 `source`는 NotebookLM 후보 단계에서는 `notebooklm_candidate`, 사람이 PDF와 chunk를 대조해 확정한 뒤에는 `manual_verified`로 두는 편이 좋습니다.

## MinerU 어댑터 사용 (격리 venv)

MinerU 는 torch/transformers 등 무거운 ML 의존성을 끌고 와 본 `Pipfile` 과 함께 lock 하면 `ResolutionTooDeepError` 가 납니다. 따라서 본 환경을 오염시키지 않고 **별도 venv** 에 설치해 사용합니다. 결정 배경은 `experiments/parser_candidates_verification.md` §9 참조.

```bash
# 1) 격리 venv 생성 + mineru 설치 (첫 1회, 수 분 소요)
python3.11 -m venv .venv-mineru
.venv-mineru/bin/pip install -U "mineru[core]"

# 2) mineru CLI 가 PATH 에 보이도록 설정 후 실험 실행
PATH=".venv-mineru/bin:$PATH" pipenv run python -m src.cli parser-compare \
  --config experiments/parser_comparison/config.example.yaml
```

- 첫 실행 시 모델 weights 약 1.1 GB 가 `~/.cache/huggingface/hub/` 에 자동 다운로드됩니다 (이후 영구 재사용).
- CPU pipeline 백엔드 기준 페이지당 약 30 초 (Apple Silicon).
- 어댑터 코드 자체는 본 환경에 있으며, 호출 시 `shutil.which("mineru")` 로 격리 venv 의 CLI 를 찾습니다.

## OpenDataLoader 어댑터 사용 (격리 venv)

OpenDataLoader 는 본 `Pipfile` 에 직접 넣지 않고 별도 venv 에 설치합니다. local 모드는 빠르지만 텍스트 레이어가 없는 안내책자형 PDF 에서는 빈 결과가 나올 수 있으므로, OCR 이 필요한 경우 hybrid backend 를 먼저 실행해야 합니다.

```bash
# 1) 격리 venv 생성 + OpenDataLoader 설치
python3.11 -m venv .venv-opendataloader
.venv-opendataloader/bin/pip install -U "opendataloader-pdf[hybrid]"

# 2) hybrid backend 실행 (OCR 필요 시)
.venv-opendataloader/bin/opendataloader-pdf-hybrid \
  --port 5002 \
  --force-ocr \
  --ocr-engine easyocr \
  --ocr-lang ko,en \
  --device cpu

# 3) parser config 에서 opendataloader 를 선택해 비교 실행
pipenv run python -m src.cli parser-compare \
  --config experiments/parser_comparison/config.example.yaml
```

- 기본 CLI 경로는 `.venv-opendataloader/bin/opendataloader-pdf` 입니다.
- hybrid 옵션은 parser config 의 `parser_options.opendataloader` 아래에 `hybrid_backend`, `hybrid_url`, `hybrid_mode`, `pages` 로 전달합니다.
- 안내책자 1~3페이지 smoke 기준: local 모드는 `text_blocks=0`, hybrid `docling-fast/full` 모드는 `text_blocks=248`, `warnings=0` 으로 정규화되었습니다.

## 설계 원칙 (Design Principles)

- 파서 비교를 애플리케이션 특정 서비스 코드와 독립적으로 유지합니다.
- 실험의 입력과 출력을 명시적으로 모델링하여 실행을 재현 가능하게 합니다.
- 파서 출력의 형태가 다르더라도 다운스트림 평가가 가능하도록 만듭니다.
- parser comparison은 빨리 검증 가능하게 만들고, retrieval 이후 단계는 작은 인터페이스로 점진 구현합니다.
- 향후 메타데이터 필터링 및 부모-자식(parent-child) 검색을 위한 여지를 남겨둡니다.

## 향후 계획 (Future Plan)

- production semantic embedding provider 연결
- UI에서 기존 리랭커 브릿지 비교 실험 전환
- 제목 인식 청킹 (heading-aware chunking)
- 부모-자식 검색 실험

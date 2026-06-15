# PDF RAG Parser Lab

PDF RAG에서 **파서 선택과 chunk 품질이 검색 랭킹에 어떤 영향을 주는지** 실험하는 저장소입니다.

이 프로젝트는 PDF를 파싱해서 RAG 데모를 만드는 데서 끝나지 않습니다. 서로 다른 PDF parser의 출력을 공통 스키마로 정규화하고, chunking과 retrieval을 거친 뒤 수동 relevance label과 `NDCG@k`로 검색 품질을 측정합니다.

## 한눈에 보기

| 항목 | 내용 |
| --- | --- |
| 목표 | parser, chunking, retrieval 품질을 분리해서 비교 |
| 주요 PDF 유형 | 텍스트 레이어가 없거나 표/달력/FAQ가 섞인 안내책자형 PDF |
| 지원 parser | `pdfplumber`, `PyMuPDF`, `MinerU`, `OpenDataLoader` |
| 공통 출력 | `ParsedDocument` 스키마 |
| 검색 | lexical in-memory, hashing embedding in-memory |
| 평가 | 수동 relevance label 기반 `NDCG@k` |
| UI | Streamlit PDF 업로드/질문/근거 검색/답변 생성 데모 |

## 현재 구현 범위

구현되어 있는 기능:

- PDF parser comparison CLI
- `pdfplumber` baseline parser adapter
- `pymupdf` parser adapter
- `mineru` parser adapter
- `opendataloader` parser adapter
- fixed-size chunker
- table chunk에 page/month context를 붙이는 실험 옵션
- lexical in-memory retrieval index
- hashing embedding 기반 in-memory retrieval index
- Retriever orchestration
- 선택적 python module reranker bridge
- `retrieval-eval` CLI와 `NDCG@k` evaluator
- Streamlit 기반 PDF 업로드/질문 데모
- `OPENAI_API_KEY` 또는 `OLLAMA_BASE` 기반 근거 답변 생성
- parsed document, parser comparison, retrieval evaluation artifact 저장

이번 포트폴리오 마감 범위에서 제외한 기능:

- production semantic embedding provider 연결
- 새 reranker model 구현
- UI에서 reranker 비교 실행/전환
- heading-aware chunking
- parent-child retrieval

## 빠른 시작

### 1. 환경 준비

기본 명령은 Pipenv 기준입니다.

```bash
pipenv install --dev
cp .env.example .env
```

일반 venv를 쓰는 경우:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

아래 예시는 `pipenv run` 기준입니다. venv를 활성화한 상태라면 `pipenv run`을 빼고 실행하면 됩니다.

### 2. Streamlit UI 실행

```bash
pipenv run streamlit run apps/parser-lab-ui/app.py
```

UI에서 할 수 있는 일:

- PDF 업로드
- parser 선택
- chunk 생성
- 검색 근거 확인
- `OPENAI_API_KEY` 또는 `OLLAMA_BASE`가 있을 때 답변 생성
- 저장된 retrieval evaluation run 비교

### 3. Parser comparison 실행

```bash
pipenv run python -m src.cli parser-compare \
  --config config.example.yaml \
  --documents /path/to/pdfs
```

### 4. Retrieval evaluation 실행

```bash
pipenv run python -m src.cli retrieval-eval \
  --config experiments/retrieval_eval/config.2026_youth_allowance_full_mineru.yaml
```

결과는 `artifacts/retrieval-eval-runs/` 아래에 저장되며 git에는 포함하지 않습니다.

### 5. 테스트와 린트

```bash
pipenv run pytest tests -q
pipenv run ruff check .
```

## 대표 평가 결과

공개 포트폴리오용 핵심 평가는 `2026 서울시 청년수당 참여자 안내책자` 전체 PDF를 대상으로 합니다. LLM 답변 품질이 아니라, **질문에 답하는 근거 chunk가 검색 결과 상위에 배치되는지**를 측정합니다.

실행 명령:

```bash
pipenv run python -m src.cli retrieval-eval \
  --config experiments/retrieval_eval/config.2026_youth_allowance_full_mineru.yaml
```

평가 조건:

| 항목 | 값 |
| --- | --- |
| 문서 | `2026 서울시 청년수당 참여자 안내책자` |
| parser | MinerU OCR |
| chunking | fixed-size + table context |
| retrieval | lexical in-memory |
| 평가셋 | 질문 8개, relevance label 26개 |
| 검색 대상 | 89 chunks, top-10 |

평균 `NDCG@k`:

| 지표 | 결과 | 해석 |
| --- | ---: | --- |
| `NDCG@1` | 0.250 | 정답 근거가 1위로 나온 질문은 2/8개 |
| `NDCG@3` | 0.363 | 일부 단답/표 질문은 상위권에 근거가 잡힘 |
| `NDCG@5` | 0.418 | 표/다중 조건 질문에서는 여전히 부족 |
| `NDCG@10` | 0.554 | 근거를 놓치기보다 후순위로 미는 문제가 큼 |

질문별 진단:

| 구분 | 질문 | 첫 관련 근거 순위 | 원인 |
| --- | --- | ---: | --- |
| 잘 됨 | 해외 생성형 AI 구독료 사후 보전 | 1위 | 고유 표현이 한 chunk에 모여 lexical 검색과 잘 맞음 |
| 잘 됨 | 자기성장기록서 미제출 불이익 | 1위 | FAQ 답변이 질문 표현과 직접 대응함 |
| 상위권 | 현금 사용 가능 항목 | 2위, 직접 근거 3위 | FAQ에도 유사 표현이 반복되어 1위가 밀림 |
| 상위권 | 자기성장기록서 제출 기간 | 2위 | 목차/안내 페이지에도 같은 표현이 자주 등장함 |
| 상위권 | 8월 자격상실신고 시 취업성공금 지급일 | 3위 | 일정 표 chunk는 잡히지만 표현이 여러 페이지와 겹침 |
| 후순위 | 취업성공금 지급 기준과 금액 | 6위, 직접 근거 9위 | 조건, 금액, 예외가 여러 근거로 나뉨 |
| 후순위 | 카드 사용 불가 업종과 개수 | 9위, 직접 근거 10위 | 긴 제한 업종 표와 반복 표현 때문에 랭킹이 밀림 |
| 후순위 | 관리비 현금 사용 증빙서류 | 8위 | 증빙서류 표는 찾지만 보완 안내 페이지와 표현이 겹침 |

참고로 1-3페이지 smoke 실험에서는 달력/지급일 질의 6개에 table context chunking을 적용했을 때 `NDCG@1/3/5 = 1.0`을 확인했습니다. 이 결과는 regression smoke 성격이며, full PDF baseline과 직접 비교하지 않습니다.

## 실험 흐름

```text
PDF
  -> parser adapter
  -> ParsedDocument
  -> chunker
  -> retrieval index
  -> optional reranker
  -> relevance labels
  -> NDCG@k evaluation
```

`retrieval-eval`은 parsed document artifact, query JSONL, relevance label JSONL을 입력으로 받아 chunking, retrieval, optional reranking, NDCG 계산을 한 번에 실행합니다.

Query와 label 예시:

```json
{"query_id":"t1_apr_payment_2","query_text":"4월 달력에서 지급②는 몇 일에 표시되어 있나요?"}
{"query_id":"t1_apr_payment_2","chunk_id":"2026-1차 참여자 안내책자:mineru:p2:table:2","grade":2}
```

라벨링 권장 절차:

1. 기준 PDF를 NotebookLM에 넣고 페이지/표/날짜/금액처럼 근거가 명확한 질문 후보를 만듭니다.
2. `data/eval/*_queries.jsonl`에 `query_id`, `query_text`, `metadata.answer_hint`, `metadata.page_range`, `metadata.needs_pdf_verification`을 기록합니다.
3. parser comparison 또는 PDF RAG UI로 같은 PDF를 파싱합니다.
4. chunk preview에서 정답 근거 chunk를 확인합니다.
5. `data/eval/*_relevance.jsonl`에 `query_id`, `chunk_id`, `grade`, `rationale`, `source`를 기록합니다.

`grade=2`는 질문에 직접 답하는 근거, `grade=1`은 부분 근거, `grade=0`은 혼동되기 쉬운 hard negative에 사용합니다. NotebookLM 단계의 `source`는 `notebooklm_candidate`, 사람이 PDF와 chunk를 대조해 확정한 뒤에는 `manual_verified`로 둡니다.

## Parser 비교 기준

| Parser | 역할 | 비고 |
| --- | --- | --- |
| `pdfplumber` | baseline parser | 기존 시스템의 참조점. 표 충실도와 구조 보존 한계를 확인하기 좋음 |
| `pymupdf` | lightweight 대안 parser | 빠른 비교 후보 |
| `mineru` | OCR 기반 parser | 텍스트 레이어가 없는 PDF 처리. 격리 venv 권장 |
| `opendataloader` | Java 기반 local/hybrid parser | OCR 필요 시 별도 hybrid backend 필요 |

목표는 parser 출력 파일만 비교하는 것이 아닙니다. parser 출력이 chunking, retrieval, NDCG 평가로 이어질 때 어떤 차이를 만드는지 확인하는 것이 핵심입니다.

## 저장소 구조

```text
pdf-rag-parser-lab/
  apps/
    parser-lab-ui/
      app.py
      components/
      views/
  src/
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
  artifacts/
  config.example.yaml
  pyproject.toml
  requirements.txt
```

## 모듈 책임

| 영역 | 책임 | 남은 일 |
| --- | --- | --- |
| `src/parsers` | parser interface, descriptor, factory | parser별 option 확장 |
| `src/chunkers` | chunker interface, chunk metadata contract | heading-aware chunking, parent-child chunking |
| `src/retrieval` | lexical/embedding in-memory index, Retriever, optional reranker bridge | production embedding provider |
| `src/evaluation` | relevance label, `NDCG@k`, query/run evaluator | 추가 metric |
| `src/metadata` | filtering과 분석을 위한 metadata contract | 공통 metadata 정규화 helper |
| `experiments/parser_comparison` | parser 비교 실행과 artifact 생성 | 품질 리포트 확장 |
| `experiments/retrieval_eval` | parsed artifact 기반 retrieval/NDCG 실행 | 추가 retrieval 전략 비교 |
| `apps/parser-lab-ui` | PDF 업로드/질문, 근거 검색, 답변 생성 데모 | 평가 결과 시각화 확장 |

## MinerU 사용

MinerU는 `torch`, `transformers` 등 무거운 ML 의존성을 끌고 오므로 본 `Pipfile`에 직접 넣지 않습니다. 별도 venv에 설치해서 사용합니다.

```bash
# 1. 격리 venv 생성과 MinerU 설치
python3.11 -m venv .venv-mineru
.venv-mineru/bin/pip install -U "mineru[core]"

# 2. mineru CLI가 PATH에 보이도록 설정 후 실행
PATH=".venv-mineru/bin:$PATH" pipenv run python -m src.cli parser-compare \
  --config experiments/parser_comparison/config.example.yaml
```

참고:

- 첫 실행 시 model weights 약 1.1 GB가 `~/.cache/huggingface/hub/`에 다운로드됩니다.
- CPU pipeline backend 기준 페이지당 약 30초가 걸립니다. Apple Silicon 기준입니다.
- adapter는 `shutil.which("mineru")`로 격리 venv의 CLI를 찾습니다.

## OpenDataLoader 사용

OpenDataLoader도 별도 venv에 설치합니다. local 모드는 빠르지만 텍스트 레이어가 없는 PDF에서는 빈 결과가 나올 수 있습니다. OCR이 필요한 경우 hybrid backend를 먼저 실행합니다.

```bash
# 1. 격리 venv 생성과 OpenDataLoader 설치
python3.11 -m venv .venv-opendataloader
.venv-opendataloader/bin/pip install -U "opendataloader-pdf[hybrid]"

# 2. OCR이 필요하면 hybrid backend 실행
.venv-opendataloader/bin/opendataloader-pdf-hybrid \
  --port 5002 \
  --force-ocr \
  --ocr-engine easyocr \
  --ocr-lang ko,en \
  --device cpu

# 3. parser config에서 opendataloader를 선택해 비교 실행
pipenv run python -m src.cli parser-compare \
  --config experiments/parser_comparison/config.example.yaml
```

참고:

- 기본 CLI 경로는 `.venv-opendataloader/bin/opendataloader-pdf`입니다.
- hybrid option은 parser config의 `parser_options.opendataloader` 아래에 `hybrid_backend`, `hybrid_url`, `hybrid_mode`, `pages`로 전달합니다.
- 안내책자 1-3페이지 smoke 기준 local 모드는 `text_blocks=0`, hybrid `docling-fast/full` 모드는 `text_blocks=248`, `warnings=0`으로 정규화되었습니다.

## 설계 원칙

- parser 비교를 application service code와 분리합니다.
- 실험 입력과 출력을 명시적으로 모델링해서 재현 가능하게 만듭니다.
- parser 출력 형태가 달라도 downstream 평가가 가능하도록 공통 스키마로 정규화합니다.
- parser comparison은 빠르게 검증하고, retrieval 이후 단계는 작은 interface로 점진 구현합니다.
- 향후 metadata filtering과 parent-child retrieval을 확장할 수 있게 남겨둡니다.

## Backlog

- production semantic embedding provider 연결
- UI에서 reranker 비교 실험 전환
- heading-aware chunking
- parent-child retrieval

# PDF RAG Parser Lab

`pdf-rag-parser-lab`은 PDF 파서 비교, 청킹(chunking) 및 검색(retrieval) 전략 테스트, 기존 리랭커(reranker) 통합, 그리고 NDCG 지향 메트릭을 통한 실행 평가를 위한 실험용 저장소입니다.

현재 단계에서는 parser comparison MVP가 구현되어 있으며, retrieval, reranker bridge, chunking, evaluation은 아직 순차적으로 구현 중입니다.

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
- parsed document / comparison artifact 저장
- 파서 비교를 위한 UI 플레이스홀더 구조

이번 단계의 범위 밖(Out of scope) 사항:

- 실제 청킹 로직
- 실제 검색 또는 벡터 인덱스 구현
- 실제 리랭커 구현
- 실제 NDCG 계산

## 베이스라인 vs 대안 파서

- `pdfplumber`: 베이스라인 파서. 기존 시스템에서 이미 시도되었으며 표 충실도와 구조 보존의 한계를 보여주었기 때문에 참조 포인트로 사용됩니다.
- `pymupdf`: 비교를 위한 대안 파서 후보.
- `opendataloader`: 향후 파서 어댑터 후보를 위한 플레이스홀더 (hybrid 모드 검증 필요).
- `mineru`: 내장 OCR 기반. 텍스트 레이어가 없는 안내책자형 PDF 처리. 무거운 ML 스택을 끌고 와서 **격리 venv `.venv-mineru/`** 에 별도 설치 (아래 섹션 참조).

목표는 단순히 파서 수준의 비교만이 아닙니다. 이 랩은 파서의 출력이 나중에 청킹, 검색, 리랭킹 및 NDCG 기반 평가로 흐를 수 있도록 설계되었습니다.

## 스캐폴드 구조 (Scaffolded Structure)

참고: 이 워크스페이스에는 새로운 랩 스캐폴드와 관련 없는 이전 프로젝트 파일이 포함되어 있을 수 있습니다. 아래 디렉토리들은 새로운 실험 중심 레이아웃을 위한 의도된 구조입니다.

```text
pdf-rag-parser-lab/
  apps/
    parser-lab-ui/
      app.py
      README.md
      components/
      pages/
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
    chunking_comparison/
    metadata_filtering/
  data/
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
| `src/parsers` | 파서 인터페이스, 파서 기술자(descriptor), 파서 팩토리 | 일부 parser만 구현됨 (`pdfplumber`, `pymupdf`) |
| `src/chunkers` | 청커 인터페이스 및 청크 메타데이터 계약 | 실제 청크 생성 로직 |
| `src/retrieval` | 임베딩, 인덱스, 리트리버, 리랭커 브릿지 인터페이스 | 임베딩 호출, 검색, 리랭크 실행 |
| `src/evaluation` | 관련성 라벨, 평가 결과 스키마, 평가기 설계 | 메트릭 계산 |
| `src/metadata` | 필터링 및 다운스트림 분석을 위한 메타데이터 계약 | 필터 실행 |
| `experiments/parser_comparison` | 파서 비교 실행 및 artifact 생성 | 동작 가능 |
| `experiments/chunking_comparison` | 청킹 비교 설정 및 오케스트레이션 엔트리포인트 | 실행 가능한 파이프라인 |
| `experiments/metadata_filtering` | 메타데이터 필터링 실험 엔트리포인트 | 실행 가능한 파이프라인 |
| `apps/parser-lab-ui` | 파서 비교 워크플로우를 위한 플레이스홀더 UI | 전체 UI 상호작용 |

## 빠른 시작 (Quick Start)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

parser comparison 예시 실행:

```bash
python -m src.cli parser-compare --config config.example.yaml
```

또는 실험 설정 파일을 직접 사용:

```bash
python -m src.cli parser-compare \
  --config experiments/parser_comparison/config.example.yaml \
  --documents data/sample_pdfs
```

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

## 설계 원칙 (Design Principles)

- 파서 비교를 애플리케이션 특정 서비스 코드와 독립적으로 유지합니다.
- 실험의 입력과 출력을 명시적으로 모델링하여 실행을 재현 가능하게 합니다.
- 파서 출력의 형태가 다르더라도 다운스트림 평가가 가능하도록 만듭니다.
- parser comparison은 빨리 검증 가능하게 만들고, retrieval 이후 단계는 작은 인터페이스로 점진 구현합니다.
- 향후 메타데이터 필터링 및 부모-자식(parent-child) 검색을 위한 여지를 남겨둡니다.

## 향후 계획 (Future Plan)

- 검색 슬라이스를 위한 메타데이터 필터링
- 제목 인식 청킹 (heading-aware chunking)
- 부모-자식 검색 실험
- 리랭커 브릿지 강화
- 파서 및 청커 조합에 대한 NDCG 기반 평가 실행

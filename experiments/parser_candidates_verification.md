# Parser Candidates 검증 — OpenDataLoader & MinerU

> **작성 시점**: 2026-05-21
> **목적**: Phase 1 (OpenDataLoader 어댑터 구현) · Phase 2 (MinerU 어댑터 추가) 진입 전,
> 두 라이브러리의 설치/실행 모델·CPU 동작·한국어 OCR 품질을 정리하여 의존성 추가 방식과 어댑터 구조를 확정한다.

---

## 1. 현재 작업 환경

| 항목 | 값 | 비고 |
| --- | --- | --- |
| OS | macOS 15.0.1 (Sequoia) | MinerU 최소 요구사항(14.0+) 충족 |
| 아키텍처 | arm64 (Apple Silicon) | MinerU `pipeline` 백엔드로 CPU 동작 가능 |
| Python | 3.11.15 | 두 라이브러리 모두 지원 |
| pipenv | 2026.0.3 | 의존성 관리 |
| Java | OpenJDK 20 | OpenDataLoader 가 JVM 프로세스 spawn — 필수 |
| 디스크 여유 | 472 GB | MinerU 모델(~20 GB) 수용 가능 |
| GPU | 없음 | 두 후보 모두 CPU 단독 동작 경로 존재 |

---

## 2. OpenDataLoader-PDF

### 2-1. 설치

```bash
# 기본 (텍스트 레이어 PDF — local mode)
pip install -U opendataloader-pdf

# 표·이미지·스캔 PDF — hybrid mode (OCR + AI backend)
pip install -U "opendataloader-pdf[hybrid]"
```

- **JVM 필수**: Python 패키지가 내부적으로 JVM 프로세스를 spawn 한다. 현재 환경의 OpenJDK 20 으로 동작 예상.
- **License**: Apache 2.0 (≥2.0 버전), 이전 버전은 MPL 2.0.

### 2-2. Python API

```python
import opendataloader_pdf

opendataloader_pdf.convert(
    input_path=["file.pdf"],
    output_dir="output/",
    format="json",   # "json,markdown" 조합 가능
)
```

- 단일 호출로 여러 파일 배치 가능 (`input_path=[...]`).
- 출력: JSON(bbox/semantic type/coords), Markdown, HTML, Tagged PDF, Annotated PDF.

### 2-3. 실행 모드 — Local vs Hybrid

| 모드 | 속도 | 용도 | 추가 인프라 |
| --- | --- | --- | --- |
| **Local** | 60+ pages/sec (CPU) | 텍스트 레이어가 살아있는 PDF | 없음 |
| **Hybrid** | 2+ pages/sec | 스캔 PDF, 복잡 표, 차트 | 별도 backend 서버 (`opendataloader-pdf-hybrid --port 5002`) |

Hybrid 는 페이지별 라우팅: 단순 페이지는 local, 복잡 페이지만 AI backend 로.
차트/이미지 설명에 **SmolVLM (256M)** 사용.

### 2-4. 한국어 / OCR

```bash
opendataloader-pdf-hybrid --port 5002 --force-ocr --ocr-lang "ko,en"
```

- 80+ 언어 지원 (한국어/일본어/중국어 명시).
- OCR 은 **hybrid 모드 전용** — local 모드에는 OCR 없음.

### 2-5. 적합도 (대상 = 표·이미지 많은 안내책자형)

- **Local 모드만으로는 부족** — 현 pdfplumber/pymupdf 과 동일한 한계 예상.
- **Hybrid 모드 필요** — 그러나 별도 서버(port 5002) 라이프사이클 관리 부담.
- 어댑터 구현 시: hybrid 서버를 subprocess 로 띄울지, 사용자가 사전에 띄우게 할지 결정 필요.

---

## 3. MinerU

### 3-1. 설치

```bash
pip install -U "mineru[all]"
# 또는 uv 사용 시
uv pip install -U "mineru[all]"
```

- 모델 가중치 **자동 다운로드** (첫 실행 시).
- 최소 디스크: 20 GB, 최소 RAM: 16 GB.
- macOS 14.0+ / Linux / Windows (WSL2) 지원.
- **License**: MinerU Open Source License (Apache 2.0 기반 + 추가 조건). v3.1.0 이전엔 AGPLv3.

### 3-2. Python API

PyPI 요약상:

```python
from mineru.api import document_parse

result = document_parse(pdf_path)
```

- 실제 호출 시그니처는 첫 실행 시점에 `help(document_parse)` 로 재확인 필요.
- CLI 가 1차 인터페이스: `mineru -p <input> -o <output> [-b pipeline]`
  - `-b pipeline`: 순수 CPU 환경 (Apple Silicon CPU-only 시 필요)

### 3-3. CPU / Apple Silicon

- `pipeline` 백엔드로 **순수 CPU 동작 가능**.
- Apple Silicon GPU 가속 경로도 존재 (Volta+ 또는 Apple Silicon).
- 현 환경은 GPU 가속을 시도해볼 수도, CPU 로 강제할 수도 있음.

### 3-4. 한국어 / OCR

- **OCR 내장** — 별도 OCR 도입 불필요.
- 스캔 PDF / 깨진 PDF 를 자동 감지하여 OCR 활성화.
- 109 개 언어 지원 (한국어 포함).
- 표 → HTML, 수식 → LaTeX 변환.

### 3-5. 적합도

- 안내책자형(표·이미지·레이아웃 복잡) 처리에 정면 대응 설계.
- 내장 OCR 로 [[Phase 0 보류항목: OCR 도입 여부]] 자동 해결.
- 모델 자동 다운로드라 **초기 1회 비용은 큼** (20 GB 디스크 + 다운로드 시간).

---

## 4. 비교 요약

| 축 | OpenDataLoader | MinerU |
| --- | --- | --- |
| 설치 단순도 | pip + JVM (이미 설치됨) | pip + 첫 실행 시 모델 다운로드 |
| 외부 의존 | JVM, hybrid 시 별도 서버 | 모델 weights (~20 GB) |
| CPU-only 동작 | ✅ local 모드 매우 빠름, hybrid 도 가능 | ✅ `pipeline` 백엔드 |
| OCR | hybrid 모드에서만 (`--force-ocr`) | 항상 내장, 자동 감지 |
| 한국어 | ✅ (`--ocr-lang ko,en`) | ✅ (109 lang 중 하나) |
| 출력 풍부도 | JSON/MD/HTML/Tagged PDF + bbox | MD/JSON + tables(HTML)/formulas(LaTeX) |
| 어댑터 복잡도 | 중간 (모드 선택, hybrid 서버 관리) | 단순 (단일 진입점) |
| 라이선스 | Apache 2.0 | Apache 2.0 (+조건) |
| 주요 리스크 | hybrid 서버 라이프사이클 | 첫 실행 시 다운로드 / 모델 크기 |

---

## 5. 의존성 추가 방식 권고

### 5-1. OpenDataLoader

- `Pipfile` 직접 추가 가능: `opendataloader-pdf = {extras = ["hybrid"], version = "*"}`
- JVM 은 시스템 의존 — `.env.example` 또는 `README` 에 OpenJDK 17+ 명시.
- Hybrid 서버는 어댑터 내부에서 subprocess 로 띄우는 방식 권장 (사용자가 별도 실행할 필요 없게).
  - 단점: 첫 호출 시 startup latency, 포트 충돌 가능성 → 어댑터 라이프사이클 명확히 설계.

### 5-2. MinerU

- `Pipfile` 직접 추가: `mineru = {extras = ["all"], version = "*"}`
- 첫 import 또는 첫 parse 시 모델 자동 다운로드 — **테스트 환경에서 별도 캐시 전략 필요** (CI 시간/네트워크 영향).
- `MINERU_MODEL_SOURCE` 등 환경 변수로 캐시 위치 제어 가능한지 후속 확인.
- 어댑터에서 강제 CPU 백엔드 옵션 노출: `mineru ... -b pipeline` 동등 인자.

### 5-3. 두 후보 동시 도입 부담

- 합산 디스크 사용량: MinerU 약 20 GB + OpenDataLoader hybrid 모델 (미확정).
- pipenv lock 시간: 두 패키지가 무거운 dependency tree 를 가져 lock 가능성 — 추가 후 lock 한 번 돌려서 확인.

---

## 6. 어댑터 구현 순서 권고

원래 Phase 순서(1: OpenDataLoader → 2: MinerU) 유지하되, **체크포인트 추가**:

### Phase 1 (OpenDataLoader) 시작 전

- [ ] **샘플 실행 확인**: 별도 가상환경에서 `pip install opendataloader-pdf` → 안내책자 PDF 1페이지 변환 → 출력 품질 정성 평가.
- [ ] **hybrid 필요 여부 결정**: local 모드만으로 표·이미지 복원이 부족하면 `[hybrid]` 도입 확정.

### Phase 2 (MinerU) 시작 전

- [ ] **샘플 실행 확인**: `pip install "mineru[all]"` → 첫 실행 시 다운로드 수용 가능 시간 측정 → 동일 PDF 변환 품질 비교.
- [ ] **CPU 백엔드 강제 시 속도** 측정 — 안내책자 한 권(예: 50 페이지) 처리 시간이 실험 사이클에 견딜 만한지.

### 양쪽 모두 샘플 통과 후

- Phase 1-1 (의존성 추가) → 1-2 (어댑터 구현) 진입.

---

## 7. 보류 항목 갱신

| 항목 | Phase 0 결과 |
| --- | --- |
| OCR 도입 여부·범위 | **결정**: MinerU 가 내장 OCR 제공 → 별도 OCR 라이브러리 도입 불필요. OpenDataLoader 는 hybrid 모드에서 자체 OCR. |
| OpenDataLoader 설치 모델 | **결정**: pip + JVM (이미 설치). hybrid 시 별도 백엔드 서버. |
| MinerU CPU 동작 | **확인**: `-b pipeline` 백엔드로 가능. 단, 속도는 샘플 실행으로 측정 필요. |

남은 보류:
- 데이터셋 relevance 라벨링 방법 (Phase 3-1 진입 시 결정).
- hybrid 서버 라이프사이클 관리 방식 (Phase 1 진입 시 결정).

---

## 8. 다음 액션

1. **샘플 실행 (별도 가상환경)** — 두 라이브러리 각각 `pip install` + 안내책자 PDF 1개 변환.
2. **품질 정성 평가** — 표·박스·이미지가 복원되는지, 한국어 깨짐 없는지.
3. **속도 측정** — 안내책자 전체(~50p) 처리 시간.
4. 결과에 따라 Phase 1 의존성 추가 확정 (Pipfile + lock).

---

## 9. 실제 실행 결과 (2026-05-21 세션)

### 9-0. 시험 환경

- 격리된 임시 venv: `/tmp/parser-trial/venv` (1.6 GB, **삭제 가능** — 본 프로젝트 `Pipfile` 미오염)
- 대상 PDF: `assets/2026-1차 참여자 안내책자.pdf` (3.8 MB, 35 페이지, 표·달력·이미지 다수)
- 본 프로젝트 변경: 이 문서 1개 추가만. 의존성·코드 변경 없음.

### 9-1. OpenDataLoader local 모드 — **실패 (텍스트 추출 불가)**

```bash
pip install opendataloader-pdf  # 22.6 MB, JVM 사용
opendataloader_pdf.convert(input_path=['...pdf'], output_dir='...', format='json,markdown')
```

- 처리 시간: 35 페이지 **4.21 초** (매우 빠름, JVM startup 포함).
- 출력: JSON 165 KB / Markdown 4.1 KB / 이미지 28개.
- **결정적 문제**: JSON 내 모든 `table cell` 의 `kids: []` — 텍스트가 한 글자도 추출되지 않음.
  - 안내책자 PDF 의 텍스트가 vector outline 또는 이미지 형태로 그려져 있어 텍스트 레이어가 사실상 없음.
  - Markdown 출력도 표 구조만 빈 셀로 보임 (`| | | | | | | |`).
- → **OpenDataLoader 는 hybrid 모드 (OCR) 가 사실상 필수**. local 모드 단독으론 안내책자형 처리 불가.

### 9-2. MinerU `pipeline` 백엔드 (CPU) — **성공 (한국어 OCR 정상)**

```bash
pip install -U "mineru[core]"   # 무거움 — torch 2.12, transformers, opencv 등 동반
mineru -p input.pdf -o output -b pipeline -l korean -s 0 -e 2  # 3페이지 샘플
```

- **모델 자동 다운로드**: `models--opendatalab--PDF-Extract-Kit-1.0` 약 **1.1 GB** 저장됨 (`~/.cache/huggingface/hub/`).
  - 영구 캐시 — 다음 세션에서 재사용. 재다운로드 불필요.
  - 실측치는 README 의 "20 GB" 보다 훨씬 작음 (core extras 기준).
- 처리 시간: 3 페이지 89 초 (모델 init 42초 1회성 + 페이지 처리 ~30 s/p).
  - 35 페이지 추정: **약 15분** (init 제외).
- 출력 품질: 한국어 텍스트 정상 추출, 달력 표가 HTML `<table>` 로 변환, 마크다운 헤딩 (`## 4월`) 자동 부여, 이미지 별도 jpg 추출.
- OCR 오인식 일부 ("1회차" → "1회찬"): RAG 평가에서 잡히긴 하지만 사용 가능 수준.

### 9-3. OpenDataLoader hybrid 모드 — **미시험**

이번 세션에서 시간/디스크 절약을 위해 보류. 안내책자형에 대해 OCR 가 필요함은 9-1 에서 확인됐고, MinerU 가 OCR 내장이라 즉시 비교 가능했음.

다음 세션에서 시험할 가치: hybrid 모드는 별도 백엔드 (Docling 또는 Hancom AI) 다운로드·서버 라이프사이클 관리 필요 → 어댑터 복잡도 증가. MinerU 가 단일 패키지로 동등 기능 제공하므로 **default 채택은 MinerU 가 유력**.

### 9-4. 결론 (Phase 1·2 우선순위 재확정)

원래 계획: **Phase 1 = OpenDataLoader 어댑터 → Phase 2 = MinerU 어댑터**.

본 검증 결과 기반 재배치 권고: **Phase 1 = MinerU 어댑터 우선 → Phase 2 = OpenDataLoader (hybrid) 어댑터 추가**.

이유:
- 안내책자형 PDF (이 repo 의 대상) 에는 OCR 가 필수 — MinerU 만 즉시 동작.
- 어댑터 복잡도: MinerU 단일 진입점 << OpenDataLoader hybrid 서버 관리.
- 비교의 의미: MinerU baseline 이 먼저 있어야 OpenDataLoader hybrid 추가 시 의미 있는 비교 가능 (현재 local 모드는 baseline 자격 없음).

### 9-6. 결과 해석 — 흔한 오해 정리 (2026-05-21 추가)

§9-1, §9-2 만 빠르게 읽으면 "OpenDataLoader 는 못 읽고 MinerU 는 잘 된다" 로 단순화되기 쉬워 명확히 정리.

**OpenDataLoader 의 두 모드 — 이번에 시험한 건 local 모드 1 가지뿐**

| 모드 | OCR | 이번 시험 | 결과 |
| --- | --- | --- | --- |
| local | 없음 (텍스트 레이어 추출만) | ✅ 했음 | 빈 셀 — 안내책자 PDF 에 텍스트 레이어 자체가 없어서 |
| hybrid | 있음 (별도 백엔드 서버) | ❌ 보류 (§9-3) | 미확인 |

→ §9-1 의 "빈 결과" 는 **라이브러리 자체의 한계가 아니라 local 모드 + 텍스트 레이어 없는 PDF 의 조합 결과**.
   pdfplumber / pymupdf 도 같은 PDF 에 같은 한계를 가짐 (OCR 이 없으므로).

**MinerU — hybrid / local 구분 자체가 없음**

- OCR 이 **내장** 되어 백엔드(`pipeline` CPU, GPU 가속 등) 와 무관하게 자동 동작.
- 이번 시험은 `pipeline` (CPU) 1 경로지만, OCR 이 같이 따라온 것뿐 "hybrid 모드" 가 아님.

**공정 비교는 아직 미완**

- 진짜 비교 = "OCR 켠 OpenDataLoader (hybrid) vs MinerU" — hybrid 시험이 §9-3 보류라 미완.
- 그러나 **어댑터 복잡도** (MinerU 단일 패키지 vs OpenDataLoader hybrid 서버 라이프사이클) 차이는 §9-4 결론에 그대로 유효.
- 즉 "Phase 1 = MinerU 우선" 결정은 품질 비교 결과가 아니라 **운영 복잡도** 근거.

---

### 9-7. 35페이지 풀변환 실측 시도 (2026-05-21 추가 — 미완)

MinerU 어댑터 (`src/parsers/mineru_parser.py`) 도입 후 안내책자 PDF **전체(35페이지)** 변환을 실측하려 했으나 mineru CLI 단에서 task fail. 어댑터까지 도달 못 함.

```
mineru -p "assets/2026-1차 참여자 안내책자.pdf" -o <tmp> -b pipeline -l korean
# Fetching 7 files: 100%  (모델 init 정상)
# resource_tracker: There appear to be 6 leaked semaphore objects
# Error: 1 task(s) failed while processing documents:
# - task#1 (2026-1차 참여자 안내책자):
```

세부 에러 메시지가 mineru CLI 측에서 잘려서 옴. 같은 PDF 의 1-3페이지(`-s 0 -e 2`) 변환은 §9-2 에서 성공한 이력이 있으므로 **페이지 수가 늘어날 때 발생하는 mineru 자체 멀티프로세싱 이슈로 추정**. 어댑터 코드의 결함은 아님 (단위 테스트 9 케이스 모두 통과).

다음 세션 행동 후보:
1. `ParserConfig.extra_options["page_range"]` 로 5~10페이지 단위로 잘라 변환 → 한계 페이지 수 파악
2. mineru CLI 를 어댑터 우회해 직접 호출, 잘리지 않은 stderr 확인
3. mineru 최신 버전 / 다른 백엔드 옵션 시험

---

### 9-5. 다음 세션 재개 지점

**시험 환경 상태**:
- `/tmp/parser-trial/venv` — 1.6 GB, 두 라이브러리 모두 설치됨. 보존 또는 `rm -rf /tmp/parser-trial` 로 삭제 가능 (다음 세션에서 다시 만들 수 있음).
- `~/.cache/huggingface/hub/models--opendatalab--PDF-Extract-Kit-1.0` — 1.1 GB 영구 캐시. **삭제 비권장** (다음 세션에서 재사용).
- 출력 샘플: `/tmp/parser-trial/odl-output/`, `/tmp/parser-trial/mineru-output-sample/` — 정성 평가 끝났으면 삭제 가능.

**다음 세션 첫 액션 후보**:
1. **(가장 자연스러움)** MinerU 어댑터 실제 구현 시작 — `src/parsers/mineru_parser.py` 신규 작성, `Pipfile` 에 `mineru` 추가, `factory.py` 등록.
2. **(보조 검증)** MinerU 35페이지 전체 변환을 한 번 돌려 실측 시간/품질 확정 후 어댑터 시작.
3. **(완전성)** OpenDataLoader hybrid 모드 시험 — 9-3 의 보류 항목 해소.
4. **(보류 항목)** Phase 3-1 의 데이터셋 relevance 라벨링 방법 결정.

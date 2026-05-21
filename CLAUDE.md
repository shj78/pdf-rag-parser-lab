# 프로젝트 하네스

> AI 에이전트와 개발자 모두가 따르는 운영 규칙.

---

## 1. 하네스 구조

이 프로젝트의 하네스는 두 축으로 구성된다.

- **Guide** — 행동 전에 방향을 잡는다. 이 문서(CLAUDE.md)와 하위 문서가 담당.
- **Sensor** — 행동 후에 관찰하고 교정한다. pre-commit hook, 린터, 에이전트 스캔이 담당.

CLAUDE.md는 advisory다 (~80% 준수율). **반드시 지켜야 할 것은 hook이나 린터로 강제한다.**

### 문서 계층

| 위치                  | 역할                         | 로드 시점         |
| --------------------- | ---------------------------- | ----------------- |
| `CLAUDE.md` (이 문서) | 프로젝트 전체 규칙           | 항상              |
| `.claude/rules/*.md`  | 도메인별 규칙 (paths 조건부) | 해당 경로 작업 시 |

### Guide 하위 문서

| 파일                        | 대상 경로 | 역할                                    |
| --------------------------- | --------- | --------------------------------------- |
| `.claude/rules/code-style.md` | `app/**` | Fowler 리팩토링 기준 코드 품질          |
| `.claude/rules/app-구조.md`   | `app/**` | route/pipeline/util 3층, 폴더·명명 규칙 |

### Sensor

| 도구       | 역할      | 강제력                        |
| ---------- | --------- | ----------------------------- |
| **black**  | 코드 포맷 | pre-commit hook               |
| **ruff**   | 린터      | pre-commit hook               |
| **테스트** | 기능 검증 | 수동 실행 (CI 구축 시 자동화) |

---

## 2. 원칙

규칙의 배경. 개별 규칙이 왜 존재하는지 판단할 때 이 원칙으로 돌아온다.

1. **변경에는 맥락이 따라다닌다** — 무엇을 바꿨는가뿐 아니라 왜 바꿨는가를 남긴다. 커밋 메시지, 실험 label, 코드 주석 모두 해당. 3주 후에 돌아왔을 때 의도를 복원할 수 있어야 한다.

2. **기록 = 실행** — 기록된 값(snapshot, 로그)과 실제 실행된 값이 반드시 일치해야 한다. 기록만 하고 제어하지 않으면 "양다리" 버그가 생긴다.

3. **점진적 강화** — 하네스는 처음부터 완벽할 필요 없다. 같은 실수가 반복되면 그때 규칙을 추가한다. 한 번의 불편으로 규칙을 만들지 않는다.

4. **"빼면 실수하는가?"** — 이 문서의 모든 항목은 이 질문을 통과해야 한다. 코드를 읽으면 알 수 있는 것, 이미 hook이 잡아주는 것은 여기 쓰지 않는다.

---

## 3. 환경

- **의존성**: `Pipfile` 관리. `pipenv run`으로 실행. `pip install` 직접 설치 금지.
- **환경 변수**: `.env`가 `config.py` 기본값을 오버라이드한다. 코드만 보면 안 되고 실제 로드된 값을 확인해야 한다.
- **Python**: 3.11

---

## 3-1. 프로젝트 경계 (이 repo는 무엇이고 무엇이 아닌가)

이 repo는 **두 레이어를 동시에 보유**한다.

| 레이어 | 위치 | 역할 |
| --- | --- | --- |
| **Production RAG 서비스** | `app/`, `eval_ragas.py`, `locustfile.py` | FastAPI 기반 PDF 업로드 → 청킹 → 임베딩 → Supabase 저장 → QA. LangSmith `traceable` + RAGAS 평가 풀세트 이미 동작 |
| **실험 워크벤치** | `src/`, `experiments/`, `apps/parser-lab-ui/` | PDF 파서 비교, 청킹 전략 비교, retrieval/평가 실험. **stub은 모두 실제 구현 대상** |

### 다른 repo와의 관계

- **`/Users/deepsea/Documents/study/python/pilab-2026-feb-sprint-2-rag`** — **설계 레퍼런스**다. 거기서 RAG 로직을 대신 처리하는 게 아니다.
  - 파이프라인 설계 결정은 그 repo의 `심혜진/래그_파이프라인_실습_후보.md`, `주간진행사항/`에 기록.
  - 두 repo의 `app/`은 거의 같은 production RAG 코드 (분기됨).
  - "RAG는 저 레포에서 한다"가 아니라 "**RAG 설계 접근법은 저 레포에 정리되어 있고, 구현은 여기서 한다**".

### 이 repo에서 실제로 구현해야 할 것 (stub → 실제)

- `src/chunkers/*` — FixedSize, MarkdownHeading 등 **`ParsedDocument`-aware 청킹**
- `src/retrieval/*` — Embedding, VectorIndex, Retriever, RerankerBridge
- `src/evaluation/*` — NDCG@k, RetrievalEvaluator, RAGAS 통합
- `src/metadata/*` — 메타데이터 필터/태깅
- `src/parsers/opendataloader_parser.py` — 어댑터 (https://github.com/opendataloader-project/opendataloader-pdf)
- `src/cli.py` 의 `chunk-compare`, `retrieval-eval` 핸들러
- `apps/parser-lab-ui/pages/*.py` — Streamlit placeholder를 실제 viewer로
- 실험 측 LangSmith 통합 (`app/main.py`의 `traceable` 패턴 참고 가능)

### 두 레이어 분업 원칙

- `app/embedding_utils.py:split_text`는 **production baseline**. 실험 목적으로 시그니처 변경 금지.
- 실험용 청킹은 `src/chunkers/`에 신규 구현. 입력은 `text: str`이 아닌 `ParsedDocument` (페이지/표/섹션 메타데이터 보존).
- production 흐름과 실험 흐름은 별도 경로. 한쪽 변경이 다른쪽 회귀를 일으키면 안 됨.

**왜 이 섹션이 있는가**: 2026-05-20 세션에서 같은 오해가 두 번 반복되어 박제한다 (실수 로그 참조).

---

## 4. 절대 금지

위반 시 즉시 멈추고 수정한다.

- API 키·시크릿을 코드에 하드코딩하지 않는다 → `.env`로만
- 동작 변경과 리팩토링을 한 커밋에 섞지 않는다
- `print()`로 디버깅하지 않는다 → `logging` 사용

---

## 5. 규칙

### 프로젝트 공통

1. **환경 복원** — 실험용으로 변경한 config, .env는 작업 완료 후 baseline으로 되돌린다.

### Hook 승격 후보

아래는 advisory 규칙이지만, 위반 시 비용이 크므로 hook으로 강제하는 것을 검토한다.

| 규칙                    | 구현 방법                          | 상태          |
| ----------------------- | ---------------------------------- | ------------- |
| `--no-verify` 커밋 차단 | `.claude/settings.json` deny       | **적용 완료** |
| `.env` 커밋 방지        | `.gitignore` (파일 자체 제외)      | **적용 완료** |

---

## 6. 냄새 신호

아래 상황이 보이면 멈추고 확인한다.

- 같은 작업을 두 번 했는데 결과가 다르다 → **환경 오염** (.env drift, config 미복원)
- 변경의 이유를 한 문장으로 설명할 수 없다 → **맥락 누락**
- 매직 넘버가 코드에 반복된다 → **상수 추출 필요** (code-style 참조)
- 이 문서가 길어지고 있다 → **분리 시점** (`.claude/rules/`로 이동)

---

## 7. 작업 루프

매 작업에서 도는 질문. 규칙이 특정 상황만 잡는다면, 질문은 비슷한 모든 상황에서 사고를 유도한다.

### 작업 전

- 이 작업에 필요한 맥락과 파일을 충분히 봤는가?
- 이 작업의 영향 범위가 어디까지인가? (app만? config도?)
- 현재 환경(config, .env)이 의도한 상태인가?

### 작업 중

- 이 변경을 3주 후에 다시 보면, 왜 이렇게 했는지 알 수 있는가?
- 여러 선택지가 있었다면 왜 이걸 골랐는지 남겼는가?
- 이 코드가 import-time에 평가되는 값에 의존하고 있지 않은가?

### 작업 후

- 이 변경이 다른 파일이나 레이어에 영향을 주는가?
- 환경이 baseline으로 복원됐는가?
- 누락된 것은 없는가?

---

## 8. 디렉토리 구조

```
project-root/
├── CLAUDE.md                   # 이 문서
├── .claude/
│   ├── settings.json           # 권한/hook 설정
│   ├── settings.local.json     # 로컬 환경 allow 리스트
│   └── rules/                  # 도메인별 규칙 (조건부 로드)
│       ├── code-style.md       # 코드 품질
│       └── app-구조.md         # 아키텍처
├── .pre-commit-config.yaml     # black + ruff 린팅/포맷팅
├── .env                        # 환경 변수 (git 제외)
├── .env.example                # .env 템플릿
├── Pipfile / Pipfile.lock      # pipenv 의존성
├── README.md
├── app/                        # FastAPI RAG 서비스
│   ├── config.py
│   ├── main.py
│   ├── embedding_utils.py
│   ├── supabase_utils.py
│   ├── exceptions.py
│   ├── static/                 # 프론트엔드 (CSS/JS)
│   └── templates/              # HTML
├── src/                        # 실험 파이프라인 라이브러리
│   ├── parsers/                # PDF 파서 (PDFPlumber, PyMuPDF 등)
│   ├── chunkers/               # 텍스트 청킹
│   ├── retrieval/              # 벡터 검색 및 리랭킹
│   ├── evaluation/             # 평가 메트릭
│   └── metadata/               # 메타데이터 유틸
├── apps/
│   └── parser-lab-ui/          # Streamlit 실험 UI
├── data/
│   └── README.md               # 데이터 디렉토리 안내
├── eval_ragas.py               # RAGAS 평가 스크립트
├── locustfile.py               # Locust 부하 테스트
└── config.example.yaml         # 실험 파이프라인 설정 예시
```

---

## 이 문서의 유지보수

- **추가 기준**: 같은 실수가 2회 이상 반복됨 / 한 번의 실수 비용이 큼 / 합의된 기준이 있음
- **추가 금지**: 특정 세션에서만 유효한 취향 / 이미 hook이 잡아주는 것 / 코드를 읽으면 알 수 있는 것
- **분리**: 특정 폴더 작업 시에만 필요하면 → `.claude/rules/` + paths. 매 작업마다 필요하면 → 여기.
- 배경/근거는 줄 수와 무관하게 유지한다. "하라/하지 마라"만 남기면 다른 맥락에서 오해된다.

---

## 실수 로그

> 실수가 발생하면 아래에 한 줄씩 추가한다.
> 처음부터 채우려 하지 않는다. 실패할 때 쌓는 것이다.
> 같은 실수가 2회 반복되면 위의 규칙이나 냄새 신호로 승격한다.

- **2026-05-20** — 사용자가 다른 repo(`pilab-2026-feb-sprint-2-rag`)를 가리키자 "RAG는 거기서 처리한다"고 단정하고 CLAUDE.md에 "이 repo에서 RAG 로직 구현 금지" 규칙을 넣으려다 거부됨. 실제로는 그 repo가 **설계 레퍼런스**고 이 repo가 실제 구현 대상. → §3-1로 승격.
- **2026-05-20** — `src/chunkers/` stub만 보고 "청킹 미구현"이라고 사용자에게 보고. 실제로는 `app/embedding_utils.py:split_text`가 production 청킹으로 이미 동작 중. **stub의 유무로 기능 유무를 판단하지 말 것** — `app/`과 `src/` 두 레이어를 모두 확인. → §3-1로 승격.

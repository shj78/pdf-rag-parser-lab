---
description: 마틴 파울러 리팩토링 기준 코드 품질 규칙. 코드 냄새 탐지와 처방.
paths:
  - "app/**"
---

# 코드 스타일

> 마틴 파울러 『Refactoring』 기반.
> 코드를 작성하거나 수정할 때 적용한다.
> 냄새(smell)를 발견하면 처방(refactoring)을 적용한다.

---

## 핵심 원칙

- **작동하는 코드보다 읽히는 코드**가 먼저다.
- 리팩토링은 기능 변경과 **반드시 분리**한다. 한 커밋에 둘 다 섞지 않는다.
- 테스트 없이 리팩토링하지 않는다. 리팩토링 전 테스트를 먼저 확인한다.

---

## 코드 냄새와 처방

### Long Method / Long Function

- **기준**: 함수 20줄 초과 (Python)
- **처방**: Extract Function — 의도를 드러내는 이름으로 분리

```python
# 냄새
async def process_video(video_path, config):
    # 40줄짜리 함수...

# 처방
async def process_video(video_path, config):
    frames = _extract_frames(video_path, config.fpm)
    descriptions = await _analyze_frames(frames, config.vision)
    return _build_context(descriptions)
```

### Long Parameter List

- **기준**: 파라미터 4개 초과
- **처방**: Introduce Parameter Object — dataclass / Pydantic BaseModel로 묶기

```python
# 냄새
def search_segments(query, model, threshold, top_k, table_name):
    ...

# 처방 — Stage Config 패턴과 자연스럽게 연결
def search_segments(query: str, cfg: RetrievalCfg | None = None):
    cfg = cfg or get_stage_config().retrieval
    ...
```

### Duplicate Code

- **기준**: 동일 로직이 2곳 이상 등장
- **처방**: Extract Function 후 단일 진실 공급원(Single Source of Truth)으로

### Feature Envy

- **기준**: 함수가 자신의 모듈보다 다른 모듈의 데이터를 더 많이 참조
- **처방**: Move Method — 데이터가 있는 모듈로 함수를 이동

### Data Clumps

- **기준**: 항상 함께 다니는 데이터 묶음
- **처방**: Extract Class / Introduce Parameter Object

```python
# 냄새 — 항상 함께 다니는 config 값들
def segment_transcript(segments, window_seconds, overlap_seconds, model_name):
    ...

# 처방 — Stage Config가 이미 이 역할
def segment_transcript(segments, cfg: EmbeddingCfg):
    ...
```

### Primitive Obsession

- **기준**: `str`로 상태/타입 표현, 매직 넘버 사용
- **처방**: Replace Primitive with Object / Introduce Constant / Enum

```python
# 냄새
if provider == "openai":
    ...
threshold = 0.5

# 처방
class Provider(str, Enum):
    OPENAI = "openai"
    OLLAMA = "ollama"

SIMILARITY_THRESHOLD = 0.5
```

### Divergent Change

- **기준**: 하나의 모듈이 서로 다른 이유로 자주 수정됨
- **처방**: 관심사별로 Extract Class — 예: config.py에 모든 stage 설정이 섞여있다면 Stage Config로 분리

### Shotgun Surgery

- **기준**: 하나의 변경이 여러 파일을 동시에 수정하게 만듦
- **처방**: Move Method / Move Field — 관련 로직을 한 곳으로

### Comments (코드 냄새로서)

- **기준**: "이 코드가 무엇을 하는지" 설명하는 주석
- **처방**: Extract Function으로 함수 이름이 주석을 대체하게 함

```python
# 냄새
# 유사도가 임계값 미만이면 fallback
if similarity < threshold:
    return fallback_results

# 처방
def _needs_fallback(similarity: float, threshold: float) -> bool:
    return similarity < threshold
```

---

## 처방 카탈로그

| 냄새 | 처방 |
|------|------|
| 20줄 초과 함수 | Extract Function |
| 파라미터 4개 초과 | Introduce Parameter Object (Stage Config) |
| 조건문 중첩 3단 이상 | Extract Function + Early Return |
| 같은 로직 2곳 이상 | Extract Function / Extract Module |
| 항상 함께 다니는 변수 | Extract Class / Dataclass / BaseModel |
| 매직 넘버 | Introduce Constant / Enum |
| 긴 조건 체인 (if/elif) | Replace Conditional with Polymorphism |
| None 체크 반복 | Introduce Special Case (Null Object) |

---

## 프로젝트 적용 기준

### 상수 추출

파이프라인 임계값은 리터럴로 반복하지 않는다. 의미 있는 이름의 상수로 추출한다.

```python
# 냄새
if similarity < 0.5:
    results = search_with_threshold(query, 0.35)

# 처방
PRIMARY_THRESHOLD = 0.5
FALLBACK_THRESHOLD = 0.35
```

### 에러 코드 타입화

상태·타입을 나타내는 문자열을 여러 파일에 흩뿌리지 않는다.

```python
class ErrorCode(str, Enum):
    CONFIG_DRIFT = "CONFIG_DRIFT"
    FIXTURE_STALE = "FIXTURE_STALE"
    SNAPSHOT_MISMATCH = "SNAPSHOT_MISMATCH"
```

### Early Return

중첩을 줄이고 정상 경로를 명확히 한다.

```python
# 냄새
def process(data):
    if data:
        if data.is_valid():
            result = compute(data)
            if result:
                return result
    return None

# 처방
def process(data):
    if not data or not data.is_valid():
        return None
    result = compute(data)
    return result if result else None
```

---

## 절대 하지 않는 것

- 동작 변경과 리팩토링을 한 커밋에 섞기
- 테스트 없이 Extract Class / Move Method 적용
- "나중에 쓸 것 같아서" 추상화 — YAGNI
- 한 PR에서 리팩토링 범위를 무한정 확장 — 요청받은 범위만 수정
- 임계값을 리터럴로 복붙

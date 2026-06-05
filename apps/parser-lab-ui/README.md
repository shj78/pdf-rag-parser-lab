# 파서 실험 UI

파서 비교 실험을 실행하고 생성된 JSON artifact를 확인하는 Streamlit UI입니다. 파서 산출물을 fixed-size chunk로 나눈 뒤 로컬 lexical 검색과 메타데이터 필터링까지 확인할 수 있습니다.

## 실행

```bash
pipenv run streamlit run apps/parser-lab-ui/app.py
```

## 상태

- 파서 비교: 실행 가능
- 검색 평가: 로컬 lexical 검색 MVP 가능
- 메타데이터 필터링: 파서명, 페이지, chunk 유형, 표 여부 기준 필터 가능
- CLI: NDCG 기반 retrieval evaluation 실행 가능
- UI: QA 답변 생성, 리랭킹, 정량 NDCG 결과 표시는 아직 미연결

## 공개 레포 메모

UI 실행 결과는 `artifacts/parser-lab-ui-runs/` 아래에 저장되며 git에는 포함하지 않습니다. 공개 저장소에서는 소스 PDF와 생성 artifact 없이 코드, 설정, 테스트, 평가 라벨만 공유하는 것을 기본으로 합니다.

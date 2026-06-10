# PDF 질문 UI

PDF 업로드 기반 RAG 데모용 Streamlit UI입니다. 파서 산출물을 fixed-size chunk로 나눈 뒤 로컬/임베딩 검색, 근거 기반 답변 생성을 시험할 수 있습니다.

## 실행

```bash
pipenv run streamlit run apps/parser-lab-ui/app.py
```

## 상태

- PDF 질문: 업로드, 파서 선택, chunk 생성, 검색, 근거 표시 가능
- 답변 생성: `OPENAI_API_KEY` 또는 `OLLAMA_BASE`가 있으면 LLM 답변 생성 가능
- 검색 품질 평가: UI에 노출하지 않고 메인 README와 `retrieval-eval` CLI로 관리
- UI 미연결: reranker on/off 비교 실행 전환

## 공개 레포 메모

UI 실행 결과는 `artifacts/parser-lab-ui-runs/`와 `artifacts/retrieval-eval-runs/` 아래에 저장되며 git에는 포함하지 않습니다. 공개 저장소에서는 소스 PDF와 생성 artifact 없이 코드, 설정, 테스트, 평가 라벨만 공유하는 것을 기본으로 합니다.

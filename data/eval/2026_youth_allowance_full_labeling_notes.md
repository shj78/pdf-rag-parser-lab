# 2026 Youth Allowance Full Golden Set Labeling Notes

`2026_youth_allowance_full_candidate_queries.jsonl` is a candidate golden set
drafted from NotebookLM output. `2026_youth_allowance_full_verified_queries.jsonl`
and `2026_youth_allowance_full_relevance.jsonl` are the manually verified subset
used by the full-PDF retrieval evaluation.

## Candidate-to-label decision

NDCG evaluation in this repository scores retrieved `chunk_id`s. NotebookLM can
propose questions and answer hints, but it does not know the chunk IDs generated
by each parser/chunking strategy in this lab.

Each final query needs:

- original PDF verification
- parser output inspection
- one or more relevant `chunk_id`s
- `grade` values

Q1 (`q01_월지급액_최대지원기간`) is intentionally kept only in the candidate
file. The source PDF page includes "매월 50만원 x 최대 6개월", but the current
MinerU full-document artifact missed that top-right page region even when the
CLI was run with OCR mode. This makes Q1 useful as a parser failure note, not as
a fair retrieval label for the current artifact.

## Grade guide

- `grade=2`: chunk directly contains enough evidence to answer the question
- `grade=1`: chunk contains partial evidence or one side of a multi-hop answer
- `grade=0`: hard negative that looks related but does not answer the question

For multi-hop questions, add multiple labels for the same `query_id` when the
answer requires more than one chunk.

## Final labeled set

- Query file: `data/eval/2026_youth_allowance_full_verified_queries.jsonl`
- Relevance labels: `data/eval/2026_youth_allowance_full_relevance.jsonl`
- Parser artifact:
  `artifacts/parser-lab-ui-runs/2026-youth-allowance-full-mineru-verified/parsed_documents/mineru`
- Chunker: fixed size, target 800, overlap 120, table context from page summary
- Included questions: Q2-Q9
- Relevance labels: 26 chunk labels across 8 queries
- Excluded candidate: Q1, because the current parser artifact lacks the needed
  evidence chunk

## Lexical baseline result

Config:
`experiments/retrieval_eval/config.2026_youth_allowance_full_mineru.yaml`

Run artifact:
`artifacts/retrieval-eval-runs/2026-youth-allowance-full-mineru-lexical`

Mean scores from the lexical in-memory baseline:

- `NDCG@1`: 0.250
- `NDCG@3`: 0.363
- `NDCG@5`: 0.418
- `NDCG@10`: 0.554

The easy condition-based questions Q8 and Q9 are retrieved at rank 1. Harder
multi-hop and table questions Q4-Q7 surface relevant evidence later in the
ranking, which gives a clear baseline for hybrid retrieval, table-aware chunking,
or reranker improvements.

## Reproduction flow

1. Parse the full PDF with the target parser, preferably MinerU and one baseline.
2. Build chunks with the exact chunker settings used in the experiment.
3. Inspect `chunks.json` or the Streamlit chunk preview.
4. Create `data/eval/2026_youth_allowance_full_relevance.jsonl` with verified
   `query_id`, `chunk_id`, `grade`, `rationale`, and `source=manual_verified`.
5. Run `retrieval-eval` and compare strategies in the Streamlit `평가 결과` tab.

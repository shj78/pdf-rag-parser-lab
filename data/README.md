# Data Directory

Store lightweight experiment inputs here.

Suggested layout:

```text
data/
  raw/        # ignored: source PDFs and large local files
  processed/  # ignored: generated intermediates
  cache/      # ignored: local caches
  eval/       # tracked when labels/query sets are safe to publish
```

Source PDFs are not committed by default because many public-sector or uploaded
PDFs have redistribution restrictions. Keep reproducible query sets and manual
relevance labels in `data/eval/` when they do not contain private information.

## Evaluation Files

- `*_candidate_queries.jsonl`: question and answer-hint drafts. These can come
  from NotebookLM, but they are not final NDCG labels until mapped to parser
  chunk IDs.
- `*_queries.jsonl`: verified questions ready for `retrieval-eval`.
- `*_relevance.jsonl`: manual relevance labels with `query_id`, `chunk_id`,
  `grade`, `rationale`, and `source=manual_verified`.

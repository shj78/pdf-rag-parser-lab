# Retrieval Evaluation Experiment

This experiment evaluates retrieval quality from saved parser artifacts.

## Flow

```text
ParsedDocument artifacts
-> FixedSizeChunker
-> lexical or hashing-embedding in-memory index
-> optional existing reranker bridge
-> NDCG@k evaluation
-> JSON run artifacts
```

## Inputs

- `inputs.parsed_documents_dir`: directory containing parsed document JSON files
- `inputs.query_set_path`: JSONL query set
- `inputs.relevance_labels_path`: JSONL manual relevance labels

Source PDFs and generated artifacts are intentionally excluded from git. Public
configs can be committed when the PDF source is public or when the user provides
their own parsed artifacts.

## Example

```bash
pipenv run python -m src.cli retrieval-eval \
  --config experiments/retrieval_eval/config.2026_youth_allowance_pages1_3.yaml
```

The example config uses MinerU parser artifacts for pages 1-3 of a schedule-heavy
PDF, fixed-size table chunking with calendar-month context, lexical retrieval,
and `NDCG@1/3/5`.

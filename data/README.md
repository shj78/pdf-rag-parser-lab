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

# Parser Comparison Experiment

This experiment compares parser outputs against the baseline `pdfplumber`
parser and writes JSON artifacts that can feed downstream chunking and
retrieval work.

## Goal

- compare parser-level extraction quality
- inspect text and table structure differences
- generate parsed-document artifacts and comparison summaries
- produce stable inputs for later chunking and retrieval experiments

## Expected Inputs

- input PDF directory
- parser list such as `pdfplumber`, `pymupdf`, `opendataloader`
- parser-specific options
- output directory for parsed artifacts and comparison summaries

## Expected Outputs

- parsed document artifacts per parser
- document-level comparison summaries
- run manifest and run summary metadata

## Status

Runnable MVP.

- `pdfplumber` baseline parsing implemented
- `pymupdf` parsing implemented
- `mineru` parsing implemented through an isolated `.venv-mineru/` CLI
- `opendataloader` parsing implemented through an isolated `.venv-opendataloader/` CLI
- OpenDataLoader hybrid mode requires a running `opendataloader-pdf-hybrid`
  backend before execution

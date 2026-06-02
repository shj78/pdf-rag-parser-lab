from __future__ import annotations

from pathlib import Path

import pytest

from src.retrieval.existing_reranker_bridge import (
    ExistingRerankerBridge,
    ExistingRerankerBridgeConfig,
)
from src.retrieval.reranker_adapter import RerankRequest
from src.schemas import RetrievalResult


def test_existing_reranker_bridge_calls_python_module(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_fake_reranker(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    bridge = ExistingRerankerBridge(
        ExistingRerankerBridgeConfig(
            entrypoint="fake_reranker:reverse_rerank",
        )
    )

    bridge.healthcheck()
    results = bridge.rerank(
        RerankRequest(
            query_id="q1",
            query_text="지급일",
            candidates=[
                _result("chunk-1", rank=1, text="청년수당 신청 자격"),
                _result("chunk-2", rank=2, text="1회 지급일 4월 30일"),
            ],
            top_k=1,
        )
    )

    assert len(results) == 1
    assert results[0].chunk_id == "chunk-2"
    assert results[0].rank == 1
    assert results[0].metadata["reranker_entrypoint"] == "fake_reranker:reverse_rerank"
    assert results[0].metadata["reranker_bridge_mode"] == "python_module"


def test_existing_reranker_bridge_maps_chunk_id_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_fake_reranker(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    bridge = ExistingRerankerBridge(
        ExistingRerankerBridgeConfig(entrypoint="fake_reranker:ids_only")
    )

    results = bridge.rerank(
        RerankRequest(
            query_id="q1",
            query_text="지급일",
            candidates=[
                _result("chunk-1", rank=1, text="자격 안내"),
                _result("chunk-2", rank=2, text="지급일 안내"),
            ],
            top_k=2,
        )
    )

    assert [result.chunk_id for result in results] == ["chunk-2", "chunk-1"]


def test_existing_reranker_bridge_requires_python_module_entrypoint() -> None:
    bridge = ExistingRerankerBridge(ExistingRerankerBridgeConfig(entrypoint=None))

    with pytest.raises(ValueError, match="entrypoint"):
        bridge.healthcheck()


def _write_fake_reranker(tmp_path: Path) -> None:
    (tmp_path / "fake_reranker.py").write_text(
        "\n".join(
            [
                "def reverse_rerank(query, chunks, top_n=10):",
                "    return list(reversed(chunks))[:top_n]",
                "",
                "def ids_only(query, chunks, top_n=10):",
                "    return [chunk['chunk_id'] for chunk in reversed(chunks)][:top_n]",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _result(chunk_id: str, *, rank: int, text: str) -> RetrievalResult:
    return RetrievalResult(
        query_id="q1",
        chunk_id=chunk_id,
        document_id="doc",
        parser_name="mineru",
        score=0.5,
        rank=rank,
        metadata={"text_preview": text},
    )

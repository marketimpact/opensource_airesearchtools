"""End-to-end integration: scoring + dedup + contradiction detection wired
through the agent without invoking Ollama or DuckDuckGo."""

from __future__ import annotations

import sys
import types
from pathlib import Path


def _stub_external_modules():
    if "ollama" not in sys.modules:
        m = types.ModuleType("ollama")

        class _Client:
            def __init__(self, *a, **kw):
                pass

        m.Client = _Client
        sys.modules["ollama"] = m
    if "duckduckgo_search" not in sys.modules:
        m = types.ModuleType("duckduckgo_search")

        class _DDGS:
            pass

        m.DDGS = _DDGS
        sys.modules["duckduckgo_search"] = m


_stub_external_modules()


def test_contradiction_detection_runs_after_dedup(
    tmp_path: Path,
    scenario_contradiction,
    monkeypatch,
):
    """Simulate the post-scoring slice of agent.run() to confirm new findings
    are diffed against history and contradictions land in the store."""
    from research.contradictions import detect_contradictions
    from research.dedup import deduplicate
    from research.store import WorkspaceStore

    prediction, actual = scenario_contradiction

    store = WorkspaceStore(
        history_path=tmp_path / "history.json",
        index_path=tmp_path / "index.json",
        contradictions_path=tmp_path / "contradictions.jsonl",
    )

    # Seed the prediction as prior history.
    store.save_history(
        [
            {
                **prediction,
                "source_domain": "jpmorgan.com",
            }
        ]
    )

    # Simulate today's run producing the actual print as a fresh finding.
    new_findings = [
        {
            **actual,
            "source_domain": "reuters.com",
        }
    ]
    index = store.load_index()
    deduped = deduplicate(new_findings, index)
    assert len(deduped) == 1

    history = store.load_history()
    contradictions = detect_contradictions(deduped, history)
    assert contradictions, "expected the prediction-vs-actual contradiction to fire"
    store.append_contradictions(contradictions)

    loaded = store.load_contradictions()
    assert len(loaded) == 1
    c = loaded[0]
    assert c["src_hash"] == deduped[0]["_content_hash"] or c["src_hash"] == actual["content_hash"]
    assert c["kind"] in {"directional", "numeric_divergence"}

"""Substrate-level tests: the store enforces structure and persistence only."""

from research.store import WorkspaceStore


def test_history_round_trip(tmp_store: WorkspaceStore, scenario_corroboration):
    tmp_store.save_history(scenario_corroboration)
    loaded = tmp_store.load_history()
    assert len(loaded) == 3
    assert {f["content_hash"] for f in loaded} == {"brent_en", "brent_fr", "brent_ar"}


def test_history_lookback_filters_old(tmp_store: WorkspaceStore, scenario_corroboration):
    # Make one finding deliberately old.
    scenario_corroboration[0]["date_observed"] = "2020-01-01"
    tmp_store.save_history(scenario_corroboration)
    recent = tmp_store.load_history(max_age_days=30)
    # Only the recent ones survive — but "unknown" dates always pass through.
    assert all(f["date_observed"] != "2020-01-01" for f in recent)


def test_contradictions_append_and_load(tmp_store: WorkspaceStore):
    tmp_store.append_contradictions(
        [
            {"src": "a", "dst": "b", "rationale": "magnitude divergence"},
            {"src": "c", "dst": "d", "rationale": "sign flip"},
        ]
    )
    loaded = tmp_store.load_contradictions()
    assert len(loaded) == 2
    assert loaded[0]["src"] == "a"


def test_feedback_grouping(tmp_store: WorkspaceStore):
    tmp_store.append_feedback("hash1", "useful")
    tmp_store.append_feedback("hash1", "pinned", note="key claim")
    tmp_store.append_feedback("hash2", "noise")
    grouped = tmp_store.feedback_by_hash()
    assert len(grouped["hash1"]) == 2
    assert grouped["hash2"][0]["feedback"] == "noise"

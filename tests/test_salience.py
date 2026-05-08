"""Salience must be transparent: same inputs, same score, with explainable parts."""

from research.salience import rank_findings, score_finding


def test_corroborated_finding_outranks_unverified(scenario_corroboration):
    high = scenario_corroboration[0]
    low = dict(high)
    low["composite_score"] = 1.5
    low["quality_tier"] = "Unreliable"
    low["scores"] = dict(high["scores"], corroboration=1)
    low["content_hash"] = "low"
    ranked = rank_findings([low, high], today="2026-04-04")
    assert ranked[0][0]["content_hash"] == high["content_hash"]
    assert ranked[1][0]["content_hash"] == "low"
    assert ranked[0][1].score > ranked[1][1].score


def test_open_contradiction_lifts_salience(scenario_contradiction):
    prediction, _ = scenario_contradiction
    no_pressure = score_finding(prediction, today="2026-04-15")
    with_pressure = score_finding(
        prediction,
        today="2026-04-15",
        contradictions_for_hash={
            prediction["content_hash"]: [{"kind": "directional"}]
        },
    )
    assert with_pressure.score > no_pressure.score
    assert any("contradiction" in r for r in with_pressure.reasons)


def test_stale_finding_surfaces(scenario_stale):
    fresh = score_finding(scenario_stale, today="2026-02-25")
    old = score_finding(scenario_stale, today="2026-04-15")
    assert old.components["stale_review_overdue"] > 0
    assert old.score >= fresh.score - 0.05  # staleness should not erase salience


def test_pinned_overrides_unreliable(scenario_corroboration):
    f = dict(scenario_corroboration[0])
    f["composite_score"] = 1.0
    f["quality_tier"] = "Unreliable"
    plain = score_finding(f, today="2026-04-04")
    pinned = score_finding(
        f,
        today="2026-04-04",
        feedback_for_hash={f["content_hash"]: [{"feedback": "pinned"}]},
    )
    assert pinned.score > plain.score


def test_breakdown_explains_itself(scenario_contradiction):
    prediction, _ = scenario_contradiction
    sb = score_finding(prediction, today="2026-04-15")
    text = sb.explain()
    assert "composite_score=" in text
    assert "recency=" in text

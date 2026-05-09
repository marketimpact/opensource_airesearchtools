"""Briefing must always emit anti-confabulation envelope (Pattern 8).

Tests the three golden scenarios end-to-end at the routine layer.
"""

from research.brief import render_briefing


CONFIG_FIXTURE = {
    "categories": [
        {"name": "Energy & Oil Markets"},
        {"name": "Refugee & Humanitarian"},
        {"name": "Diplomatic & Political"},
    ],
}


def test_envelope_required_even_on_empty_workspace(tmp_store):
    text = render_briefing(
        tmp_store, config=CONFIG_FIXTURE, today="2026-04-15"
    )
    assert "Anti-confabulation envelope" in text
    assert "Confidence" in text
    assert "Tool actions taken" in text
    assert "very low" in text or "low" in text  # no findings → low confidence


def test_corroboration_appears_in_briefing(populated_store):
    text = render_briefing(
        populated_store, config=CONFIG_FIXTURE, today="2026-04-04", top=10
    )
    # All three Brent crude findings should be ranked.
    assert "Brent crude rises 4.2%" in text
    # Coverage must list every represented language.
    assert "en:" in text and "fr:" in text and "ar:" in text
    # New today: the FR and AR ones are dated 2026-04-04.
    assert "New today" in text


def test_contradiction_surfaces_in_section(populated_store, scenario_contradiction):
    prediction, actual = scenario_contradiction
    populated_store.append_contradictions(
        [
            {
                "src_hash": actual["content_hash"],
                "dst_hash": prediction["content_hash"],
                "src_title": actual["title"],
                "dst_title": prediction["title"],
                "src_date": actual["date_observed"],
                "dst_date": prediction["date_observed"],
                "src_source": actual["source_name"],
                "dst_source": prediction["source_name"],
                "category": actual["category"],
                "kind": "directional",
                "rationale": "directional disagreement",
                "confidence": 0.7,
                "entity_overlap": 0.8,
                "detected_at": "2026-04-03T12:00:00Z",
            }
        ]
    )
    text = render_briefing(
        populated_store, config=CONFIG_FIXTURE, today="2026-04-15", top=10
    )
    assert "Open contradictions (1)" in text
    assert "directional" in text
    assert "stabilise" in text.lower() or "stabilise" in prediction["title"].lower()
    # The envelope must mention the contradiction count too.
    assert "Open contradictions:** 1" in text


def test_stale_finding_in_briefing(populated_store, scenario_stale):
    text = render_briefing(
        populated_store, config=CONFIG_FIXTURE, today="2026-04-15", top=10
    )
    # The EU aid finding is dated 2026-02-20, so on 2026-04-15 it's > 30d old.
    assert "Stale or review-overdue" in text
    assert scenario_stale["title"] in text


def test_missing_category_reported_as_gap(tmp_store, scenario_corroboration):
    """If config lists a category the workspace has zero findings in, the
    envelope must call it out — Pattern 8."""
    tmp_store.save_history(scenario_corroboration)
    text = render_briefing(
        tmp_store, config=CONFIG_FIXTURE, today="2026-04-04"
    )
    assert "Refugee & Humanitarian" in text  # listed under "empty"
    assert "Missing" in text


def test_briefing_does_not_write_to_history(populated_store):
    before = populated_store.load_history()
    render_briefing(populated_store, config=CONFIG_FIXTURE, today="2026-04-15")
    after = populated_store.load_history()
    assert before == after, "briefing must be read-only"

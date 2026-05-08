"""Golden scenario 2: contradicted prediction. Pattern 6, 12, 19."""

from research.contradictions import detect_contradictions


def test_contradiction_detected_on_numeric_divergence(scenario_contradiction):
    prediction, actual = scenario_contradiction
    found = detect_contradictions([actual], [prediction])
    assert len(found) == 1, f"expected one contradiction, got {len(found)}"
    c = found[0]
    assert c["kind"] in {"numeric_divergence", "directional"}
    assert c["src_hash"] == actual["content_hash"]
    assert c["dst_hash"] == prediction["content_hash"]
    assert 0.4 <= c["confidence"] <= 0.95


def test_numeric_divergence_when_no_directional_signal(scenario_contradiction):
    """Without directional verbs, numeric divergence should fire on its own."""
    prediction, actual = scenario_contradiction
    p2 = dict(prediction)
    p2["title"] = "Brent crude expected near $90 by April"
    p2["details"] = "Brent crude is expected near $90 per barrel by April per JPM models."
    a2 = dict(actual)
    a2["title"] = "Brent crude reaches $127/barrel after Hormuz tensions"
    a2["details"] = "Brent crude futures reached $127.30 amid Iranian naval activity near Hormuz."
    found = detect_contradictions([a2], [p2])
    assert len(found) == 1
    assert found[0]["kind"] == "numeric_divergence"
    assert "$90" in found[0]["rationale"] and "$127" in found[0]["rationale"]


def test_corroboration_does_not_trigger_contradiction(scenario_corroboration):
    """Three sources agreeing on $127 must NOT produce contradictions."""
    en, fr, ar = scenario_corroboration
    found = detect_contradictions([fr, ar], [en])
    assert found == [], f"expected no contradictions among agreeing sources, got {found}"


def test_same_source_skipped(scenario_corroboration):
    """A finding cannot contradict another from the same domain."""
    en = scenario_corroboration[0]
    twin = dict(en)
    twin["content_hash"] = "brent_en_twin"
    twin["details"] = en["details"].replace("$127.30", "$200.00")
    found = detect_contradictions([twin], [en])
    assert found == [], "same-domain pairs must be ignored"


def test_low_entity_overlap_skipped(scenario_contradiction):
    """No shared entities means no contradiction even with disagreeing numbers."""
    prediction, actual = scenario_contradiction
    unrelated = dict(actual)
    unrelated["key_entities"] = ["uranium", "iaea", "vienna"]
    unrelated["title"] = "IAEA reports uranium enrichment at Natanz"
    unrelated["details"] = "IAEA inspectors verified $0 in new equipment at Natanz."
    unrelated["content_hash"] = "iaea_natanz"
    found = detect_contradictions([unrelated], [prediction])
    assert found == []


def test_directional_disagreement_caught(scenario_contradiction):
    """Directional check must run before weak numeric divergence."""
    prediction, actual = scenario_contradiction
    found = detect_contradictions([actual], [prediction])
    assert len(found) == 1
    # The numeric divergence (90 vs 127) is real, but directional ('rises' vs
    # 'stabilise') is the cleaner signal and should win.
    assert found[0]["kind"] == "directional"

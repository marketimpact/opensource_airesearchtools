"""Shared constants used across scorer, briefing, salience, and contradiction routines.

Centralised here so the briefing surfaces the exact same tier names and thresholds
the scorer uses. Override values in configs/research-agent.yaml; never hard-code in
multiple modules.
"""

DEFAULT_WEIGHTS = {
    "source_reliability": 0.30,
    "corroboration": 0.25,
    "specificity": 0.20,
    "recency": 0.15,
    "geographic_relevance": 0.10,
}

TIER_THRESHOLDS = {
    "Verified": 4.0,
    "Likely": 3.0,
    "Unverified": 2.0,
    # Below 2.0 = "Unreliable"
}

TIER_ORDER = ["Verified", "Likely", "Unverified", "Unreliable"]

DEFAULT_MIN_COMPOSITE_SCORE = 2.0

DEFAULT_HISTORY_LOOKBACK_DAYS = 30


def classify_tier(composite: float) -> str:
    """Map a composite score to a quality tier name."""
    if composite >= TIER_THRESHOLDS["Verified"]:
        return "Verified"
    if composite >= TIER_THRESHOLDS["Likely"]:
        return "Likely"
    if composite >= TIER_THRESHOLDS["Unverified"]:
        return "Unverified"
    return "Unreliable"

"""Salience as a transparent workflow (Pattern 10).

Given a finding plus context (open contradictions on it, feedback history,
today's date), return a salience score in [0, 1] together with a breakdown the
briefing can print verbatim. No hidden magic numbers — weights live in
configs/salience.yaml.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

from research.constants import TIER_THRESHOLDS

log = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "weights": {
        "composite_score": 0.30,
        "recency": 0.20,
        "corroboration": 0.15,
        "contradiction_pressure": 0.20,
        "stale_review_overdue": 0.15,
    },
    "boost": {"pinned": 0.20, "cross_language_corroborated": 0.10},
    "penalty": {"noise": 0.30, "unreliable_tier": 0.40},
    "stale_after_days": 30,
    "fresh_corroborator_days": 14,
}


@dataclass
class SalienceBreakdown:
    score: float
    components: dict[str, float] = field(default_factory=dict)
    boosts: dict[str, float] = field(default_factory=dict)
    penalties: dict[str, float] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)

    def explain(self) -> str:
        parts = []
        for name, val in self.components.items():
            if val:
                parts.append(f"{name}={val:.2f}")
        for name, val in self.boosts.items():
            parts.append(f"+{name}={val:.2f}")
        for name, val in self.penalties.items():
            parts.append(f"-{name}={val:.2f}")
        return ", ".join(parts)


def load_salience_config(path: Path | None = None) -> dict:
    if path is None:
        path = Path(__file__).resolve().parent.parent / "configs" / "salience.yaml"
    if not Path(path).exists():
        log.warning(f"Salience config missing at {path}, using defaults.")
        return DEFAULT_CONFIG
    with open(path) as f:
        return yaml.safe_load(f) or DEFAULT_CONFIG


def score_finding(
    finding: dict,
    *,
    config: dict | None = None,
    contradictions_for_hash: dict[str, list[dict]] | None = None,
    feedback_for_hash: dict[str, list[dict]] | None = None,
    cross_language_corroborators: bool = False,
    today: str | None = None,
) -> SalienceBreakdown:
    """Compute salience for a single finding with full provenance of the score."""
    cfg = config or DEFAULT_CONFIG
    w = cfg["weights"]
    boost_cfg = cfg.get("boost", {})
    penalty_cfg = cfg.get("penalty", {})

    today_date = _parse_date(today) if today else datetime.now(timezone.utc).date()

    h = finding.get("content_hash") or finding.get("_content_hash") or ""
    contradictions = (contradictions_for_hash or {}).get(h, [])
    feedback = (feedback_for_hash or {}).get(h, [])

    components = {
        "composite_score": _norm_composite(finding.get("composite_score", 0)),
        "recency": _recency_score(finding.get("date_observed", "unknown"), today_date),
        "corroboration": _norm_subscore(finding.get("scores", {}).get("corroboration", 0)),
        "contradiction_pressure": 1.0 if contradictions else 0.0,
        "stale_review_overdue": _stale_score(
            finding,
            today_date,
            stale_days=cfg.get("stale_after_days", 30),
        ),
    }

    weighted = sum(components[k] * w.get(k, 0.0) for k in components)

    boosts: dict[str, float] = {}
    if any(f.get("feedback") == "pinned" for f in feedback):
        boosts["pinned"] = boost_cfg.get("pinned", 0.0)
    if cross_language_corroborators:
        boosts["cross_language_corroborated"] = boost_cfg.get(
            "cross_language_corroborated", 0.0
        )

    penalties: dict[str, float] = {}
    noise_count = sum(1 for f in feedback if f.get("feedback") == "noise")
    if noise_count >= 2:
        penalties["noise"] = penalty_cfg.get("noise", 0.0)
    if finding.get("quality_tier") == "Unreliable":
        penalties["unreliable_tier"] = penalty_cfg.get("unreliable_tier", 0.0)

    score = weighted + sum(boosts.values()) - sum(penalties.values())
    score = max(0.0, min(1.0, score))

    reasons = _build_reasons(components, boosts, penalties, contradictions)

    return SalienceBreakdown(
        score=round(score, 3),
        components={k: round(v, 3) for k, v in components.items()},
        boosts={k: round(v, 3) for k, v in boosts.items()},
        penalties={k: round(v, 3) for k, v in penalties.items()},
        reasons=reasons,
    )


def rank_findings(
    findings: list[dict],
    *,
    config: dict | None = None,
    contradictions_for_hash: dict[str, list[dict]] | None = None,
    feedback_for_hash: dict[str, list[dict]] | None = None,
    cross_language_hashes: set[str] | None = None,
    today: str | None = None,
) -> list[tuple[dict, SalienceBreakdown]]:
    """Return findings paired with their salience breakdown, ranked desc."""
    cfg = config or DEFAULT_CONFIG
    cross_lang = cross_language_hashes or set()
    out: list[tuple[dict, SalienceBreakdown]] = []
    for f in findings:
        h = f.get("content_hash") or f.get("_content_hash") or ""
        breakdown = score_finding(
            f,
            config=cfg,
            contradictions_for_hash=contradictions_for_hash,
            feedback_for_hash=feedback_for_hash,
            cross_language_corroborators=h in cross_lang,
            today=today,
        )
        out.append((f, breakdown))
    out.sort(key=lambda pair: pair[1].score, reverse=True)
    return out


# --- component scorers ---


def _norm_composite(score: float) -> float:
    """Map composite (1.0–5.0) onto [0, 1]."""
    return max(0.0, min(1.0, (score - 1.0) / 4.0))


def _norm_subscore(score: int | float) -> float:
    """Map a 1–5 sub-score onto [0, 1]."""
    return max(0.0, min(1.0, (float(score) - 1.0) / 4.0))


def _recency_score(date_str: str, today):
    if date_str == "unknown":
        return 0.0
    d = _parse_date(date_str)
    if d is None:
        return 0.0
    delta = (today - d).days
    if delta <= 0:
        return 1.0
    if delta >= 30:
        return 0.0
    return max(0.0, 1.0 - delta / 30.0)


def _stale_score(finding: dict, today, stale_days: int) -> float:
    """1.0 when this finding is overdue for review.

    A finding is considered overdue when:
    - it has an explicit review_date that has passed, OR
    - its date_observed is older than stale_days days AND
      it received no fresh corroborator (caller signals this via the recency
      sub-score being low; we keep this purely date-based for v1).
    """
    review = finding.get("review_date")
    if review:
        d = _parse_date(review)
        if d is not None and d <= today:
            return 1.0
    date_obs = finding.get("date_observed", "unknown")
    if date_obs == "unknown":
        return 0.0
    d = _parse_date(date_obs)
    if d is None:
        return 0.0
    age = (today - d).days
    if age <= stale_days:
        return 0.0
    # Soft ramp: 0 at stale_days, 1 at 2*stale_days.
    return min(1.0, (age - stale_days) / stale_days)


def _build_reasons(components, boosts, penalties, contradictions) -> list[str]:
    reasons: list[str] = []
    if components["contradiction_pressure"] > 0:
        reasons.append(
            f"{len(contradictions)} open contradiction(s)"
        )
    if components["stale_review_overdue"] >= 0.5:
        reasons.append("stale or review overdue")
    if components["recency"] >= 0.7:
        reasons.append("fresh")
    if components["composite_score"] >= 0.7:
        reasons.append("high quality score")
    if boosts.get("pinned"):
        reasons.append("pinned by user")
    if boosts.get("cross_language_corroborated"):
        reasons.append("cross-language corroboration")
    if penalties.get("noise"):
        reasons.append("similar items marked noise")
    if penalties.get("unreliable_tier"):
        reasons.append("unreliable tier")
    return reasons


def _parse_date(s: str):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


# Re-exported for the briefing's "what counts as Likely" caveat line.
def _is_at_least_likely(finding: dict) -> bool:
    return finding.get("composite_score", 0) >= TIER_THRESHOLDS["Likely"]

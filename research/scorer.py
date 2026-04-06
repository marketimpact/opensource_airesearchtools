"""Multi-dimensional scoring and ground-truth validation for findings."""

import json
import logging
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse

import yaml

log = logging.getLogger(__name__)

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

# Regex patterns for specificity scoring
RE_NUMBERS = re.compile(
    r"\$\d[\d,]*\.?\d*"  # Dollar amounts like $127.30
    r"|\d[\d,]*\.?\d*\s*"
    r"(%|percent|billion|million|thousand|trillion|barrel|bpd|bbl"
    r"|tonnes?|tons?|km|miles?|MW|GW|USD|EUR|GBP)",
    re.IGNORECASE,
)
RE_DATES = re.compile(
    r"\d{4}-\d{2}-\d{2}"
    r"|(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2}(?:,?\s+\d{4})?"
    r"|Q[1-4]\s+\d{4}",
    re.IGNORECASE,
)
RE_PROPER_NOUNS = re.compile(r"(?<![.!?]\s)(?<!\A)(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)")

# Superlative language that weakens specificity without data
RE_SUPERLATIVES = re.compile(
    r"\b(unprecedented|historic|worst ever|never before|massive|enormous|catastrophic)\b",
    re.IGNORECASE,
)

# Language-to-region mapping for geographic relevance
LANGUAGE_REGION_MAP = {
    "fa": ["Iran", "Middle East"],
    "ar": ["Middle East", "Gulf States", "Arab World"],
    "tr": ["Turkey", "Middle East"],
    "ru": ["Russia"],
    "zh": ["China", "Asia"],
    "fr": ["France", "Europe", "Africa"],
    "en": ["Global"],
}


def load_authority_db(path: Path) -> dict:
    """Load the source authority database."""
    if not path.exists():
        log.warning(f"Authority DB not found at {path}, using empty DB")
        return {"by_domain": {}, "by_name": {}, "tld_defaults": {}}
    with open(path) as f:
        return yaml.safe_load(f)


def load_history(path: Path, max_age_days: int = 30) -> list[dict]:
    """Load recent findings history for corroboration checking."""
    if not path.exists():
        return []
    try:
        with open(path) as f:
            data = json.load(f)
        findings = data.get("findings", [])
        # Filter to recent entries
        cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).strftime("%Y-%m-%d")
        return [f for f in findings if f.get("date_observed", "unknown") >= cutoff or f.get("date_observed") == "unknown"]
    except (json.JSONDecodeError, KeyError) as e:
        log.warning(f"Failed to load history: {e}")
        return []


def save_history(path: Path, existing_history: list[dict], new_findings: list[dict]):
    """Append new scored findings to the history store."""
    path.parent.mkdir(parents=True, exist_ok=True)

    for f in new_findings:
        existing_history.append({
            "content_hash": f.get("_content_hash", ""),
            "title": f.get("title", ""),
            "category": f.get("category", ""),
            "impact_type": f.get("impact_type", ""),
            "date_observed": f.get("date_observed", "unknown"),
            "source_domain": _extract_domain(f.get("source_url", "")),
            "source_language": f.get("source_language", ""),
            "related_regions": f.get("related_regions", []),
            "key_entities": list(_extract_entities(f.get("title", "") + " " + f.get("details", ""))),
            "composite_score": f.get("composite_score", 0),
            "scores": f.get("scores", {}),
        })

    data = {
        "findings": existing_history,
        "meta": {
            "total_findings": len(existing_history),
            "last_updated": datetime.now(timezone.utc).isoformat(),
        },
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def score_findings(
    findings: list[dict],
    authority_db: dict,
    history: list[dict],
    run_date: str,
    weights: dict | None = None,
) -> list[dict]:
    """Score each finding across 5 dimensions. Adds scores in-place."""
    w = weights or DEFAULT_WEIGHTS

    # Pre-compute entity sets for all findings (for corroboration)
    entity_cache = {}
    for i, f in enumerate(findings):
        text = f.get("title", "") + " " + f.get("details", "")
        entity_cache[i] = _extract_entities(text)

    # Pre-compute history entity sets
    history_entities = []
    for h in history:
        history_entities.append(set(h.get("key_entities", [])))

    for i, f in enumerate(findings):
        scores = {
            "source_reliability": _score_source_reliability(f, authority_db),
            "corroboration": _score_corroboration(i, findings, entity_cache, history, history_entities),
            "specificity": _score_specificity(f),
            "recency": _score_recency(f, run_date),
            "geographic_relevance": _score_geographic_relevance(f, authority_db),
        }

        # Apply heuristic adjustments
        _apply_heuristic_adjustments(f, scores)

        # Clamp scores to 1-5
        for key in scores:
            scores[key] = max(1, min(5, scores[key]))

        composite = sum(scores[dim] * w.get(dim, 0) for dim in scores)
        tier = _classify_tier(composite)

        f["scores"] = scores
        f["composite_score"] = round(composite, 2)
        f["quality_tier"] = tier

    return findings


# --- Dimension Scorers ---

def _score_source_reliability(finding: dict, authority_db: dict) -> int:
    """Score based on source authority database lookup."""
    url = finding.get("source_url", "")
    name = finding.get("source_name", "")
    domain = _extract_domain(url)

    # Try domain lookup
    by_domain = authority_db.get("by_domain", {})
    if domain in by_domain:
        return by_domain[domain].get("tier", 2)

    # Try subdomain stripping (e.g., "www.reuters.com" -> "reuters.com")
    parts = domain.split(".")
    if len(parts) > 2:
        short_domain = ".".join(parts[-2:])
        if short_domain in by_domain:
            return by_domain[short_domain].get("tier", 2)

    # Try name lookup (case-insensitive substring)
    by_name = authority_db.get("by_name", {})
    name_lower = name.lower()
    for known_name, info in by_name.items():
        if known_name.lower() in name_lower or name_lower in known_name.lower():
            return info.get("tier", 2)

    # TLD fallback
    tld_defaults = authority_db.get("tld_defaults", {})
    for tld, tier in tld_defaults.items():
        if domain.endswith(tld):
            return tier

    return 1  # Unknown source


def _score_corroboration(
    idx: int,
    findings: list[dict],
    entity_cache: dict[int, set],
    history: list[dict],
    history_entities: list[set],
) -> int:
    """Score based on cross-referencing with other findings and history."""
    f = findings[idx]
    my_entities = entity_cache[idx]
    my_domain = _extract_domain(f.get("source_url", ""))
    my_category = f.get("category", "")
    my_lang = f.get("source_language", "")

    if not my_entities:
        return 1

    # Within-run corroboration
    same_run_matches = []
    for j, other in enumerate(findings):
        if j == idx:
            continue
        if other.get("category", "") != my_category:
            continue
        other_domain = _extract_domain(other.get("source_url", ""))
        if other_domain == my_domain:
            continue  # Same source doesn't count
        similarity = _jaccard(my_entities, entity_cache.get(j, set()))
        if similarity >= 0.35:
            same_run_matches.append({
                "lang": other.get("source_language", ""),
                "domain": other_domain,
            })

    # Historical corroboration
    historical_matches = 0
    for h_idx, h in enumerate(history):
        if h.get("category", "") != my_category:
            continue
        if h.get("source_domain", "") == my_domain:
            continue
        similarity = _jaccard(my_entities, history_entities[h_idx])
        if similarity >= 0.30:
            historical_matches += 1

    # Count unique corroborating domains
    unique_domains = {m["domain"] for m in same_run_matches}
    cross_language = len({m["lang"] for m in same_run_matches if m["lang"] != my_lang}) > 0

    total_corroborators = len(unique_domains) + min(historical_matches, 2)  # Cap historical contribution

    if total_corroborators >= 3 and cross_language:
        return 5
    elif total_corroborators >= 2 and cross_language:
        return 4
    elif total_corroborators >= 2:
        return 3
    elif total_corroborators >= 1 or historical_matches >= 1:
        return 2
    else:
        return 1


def _score_specificity(finding: dict) -> int:
    """Score based on concrete data markers in the finding."""
    text = finding.get("title", "") + " " + finding.get("details", "")

    markers = 0
    markers += len(RE_NUMBERS.findall(text))
    markers += len(RE_DATES.findall(text))
    markers += len(RE_PROPER_NOUNS.findall(text))

    if markers == 0:
        return 1
    elif markers == 1:
        return 2
    elif markers == 2:
        return 3
    elif markers <= 4:
        return 4
    else:
        return 5


def _score_recency(finding: dict, run_date: str) -> int:
    """Score based on how recent the finding is."""
    date_str = finding.get("date_observed", "unknown")
    if date_str == "unknown":
        return 1

    try:
        observed = datetime.strptime(date_str, "%Y-%m-%d").date()
        run = datetime.strptime(run_date, "%Y-%m-%d").date()
        delta = (run - observed).days

        if delta <= 0:
            return 5
        elif delta <= 2:
            return 4
        elif delta <= 7:
            return 3
        elif delta <= 30:
            return 2
        else:
            return 1
    except ValueError:
        return 1


def _score_geographic_relevance(finding: dict, authority_db: dict) -> int:
    """Score based on source region vs. finding's related regions."""
    source_lang = finding.get("source_language", "")
    related_regions = [r.lower() for r in finding.get("related_regions", [])]
    source_url = finding.get("source_url", "")
    domain = _extract_domain(source_url)

    if not related_regions:
        return 2

    # Get source's geographic focus from authority DB
    by_domain = authority_db.get("by_domain", {})
    source_geo = []
    if domain in by_domain:
        source_geo = [g.lower() for g in by_domain[domain].get("geographic_focus", [])]
    elif len(domain.split(".")) > 2:
        short = ".".join(domain.split(".")[-2:])
        if short in by_domain:
            source_geo = [g.lower() for g in by_domain[short].get("geographic_focus", [])]

    # Also use language-region mapping
    lang_regions = [r.lower() for r in LANGUAGE_REGION_MAP.get(source_lang, [])]

    # Check for direct overlap
    all_source_regions = set(source_geo + lang_regions)

    if "global" in all_source_regions:
        return 3  # Global sources get a baseline of 3

    overlap = all_source_regions & set(related_regions)
    if overlap:
        # Direct match between source region and affected region
        return 5 if source_lang != "en" else 4  # Local language sources get higher score
    else:
        return 1


def _apply_heuristic_adjustments(finding: dict, scores: dict):
    """Apply penalty adjustments for red flags."""
    text = finding.get("details", "")

    # Superlatives without specific data
    if RE_SUPERLATIVES.search(text) and scores["specificity"] <= 2:
        scores["specificity"] = max(1, scores["specificity"] - 1)

    # Date inconsistency: unknown date but urgent language
    if finding.get("date_observed") == "unknown":
        urgent_words = re.search(r"\b(breaking|just reported|just announced|moments ago)\b", text, re.IGNORECASE)
        if urgent_words:
            scores["recency"] = 1
            scores["specificity"] = max(1, scores["specificity"] - 1)


# --- Utility Functions ---

def _extract_domain(url: str) -> str:
    """Extract domain from URL."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path
        domain = domain.lower().removeprefix("www.")
        return domain
    except Exception:
        return ""


def _extract_entities(text: str) -> set[str]:
    """Extract key entities from text for corroboration matching."""
    entities = set()

    # Numbers with context
    for match in RE_NUMBERS.finditer(text):
        entities.add(match.group().strip().lower())

    # Proper noun phrases
    for match in RE_PROPER_NOUNS.finditer(text):
        entities.add(match.group().strip().lower())

    # Significant standalone numbers (prices, percentages)
    for match in re.finditer(r"\$[\d,.]+|\d+\.?\d*%", text):
        entities.add(match.group().strip().lower())

    return entities


def _jaccard(set_a: set, set_b: set) -> float:
    """Compute Jaccard similarity between two sets."""
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


def _classify_tier(composite: float) -> str:
    """Map composite score to quality tier."""
    if composite >= TIER_THRESHOLDS["Verified"]:
        return "Verified"
    elif composite >= TIER_THRESHOLDS["Likely"]:
        return "Likely"
    elif composite >= TIER_THRESHOLDS["Unverified"]:
        return "Unverified"
    else:
        return "Unreliable"

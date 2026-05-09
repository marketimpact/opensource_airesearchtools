"""Detect contradictions between findings.

Pattern 6 (Structural Alert Propagation) + Pattern 19 (Local Validity, Global
Coherence). The corroboration scorer already detects entity overlap; this module
is its mirror image: when entities overlap but numeric magnitudes or directional
language disagree, emit a contradiction.

Design rule: rule-based, deterministic, transparent. No LLM calls. False positives
are surfaced as "possible contradictions" in the briefing, not as facts.
"""

import logging
import re
from datetime import datetime, timezone
from typing import Iterable

log = logging.getLogger(__name__)

DEFAULT_ENTITY_OVERLAP = 0.30
DEFAULT_NUMERIC_DIVERGENCE = 1.30  # max/min ratio threshold
DEFAULT_PERCENT_DIVERGENCE = 2.0   # percentage-point gap threshold

DIRECTION_RISE = {
    "rise", "rises", "rose", "rising",
    "spike", "spikes", "spiked", "spiking",
    "surge", "surges", "surged", "surging",
    "jump", "jumps", "jumped", "jumping",
    "climb", "climbs", "climbed", "climbing",
    "soar", "soars", "soared", "soaring",
    "rally", "rallied", "rallying",
    "increase", "increases", "increased", "increasing",
}
DIRECTION_FALL = {
    "fall", "falls", "fell", "falling",
    "drop", "drops", "dropped", "dropping",
    "decline", "declines", "declined", "declining",
    "plunge", "plunges", "plunged", "plunging",
    "tumble", "tumbles", "tumbled", "tumbling",
    "slip", "slips", "slipped", "slipping",
    "decrease", "decreases", "decreased", "decreasing",
    "ease", "eased", "easing",
}
DIRECTION_STABLE = {
    "stabilise", "stabilises", "stabilised", "stabilising",
    "stabilize", "stabilizes", "stabilized", "stabilizing",
    "steady", "steadied", "unchanged", "flat",
}

NEGATION_AGREEMENT_PAIRS = [
    ({"agreed", "agree", "accepts", "accepted", "approved", "approves",
      "ratified", "endorsed", "endorses"},
     {"rejected", "rejects", "denied", "denies", "declined", "refused",
      "refuses", "vetoed", "blocked"}),
    ({"escalate", "escalates", "escalated", "escalation"},
     {"de-escalate", "deescalate", "deescalation", "de-escalation",
      "ceasefire", "truce"}),
]

RE_DOLLAR = re.compile(r"\$\s?(\d[\d.,]*)")
# Numbers using either '.' or ',' as decimal separator. Matches "4,2" as well as
# "4.2"; matches "127,30" as 127.30 and "127.30" as 127.30.
RE_PERCENT = re.compile(r"(\d+(?:[.,]\d+)?)\s?%")
RE_WORDS = re.compile(r"[A-Za-z\-]+")


def _parse_number(raw: str) -> float | None:
    """Parse '4,2' or '4.2' or '127,30' or '1,234.56' as a float."""
    s = raw.strip()
    if not s:
        return None
    has_dot = "." in s
    has_comma = "," in s
    if has_dot and has_comma:
        # Assume thousands separator + decimal: format "1,234.56".
        s = s.replace(",", "")
    elif has_comma and not has_dot:
        # European style: comma is decimal separator.
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def detect_contradictions(
    new_findings: list[dict],
    history: list[dict],
    entity_overlap: float = DEFAULT_ENTITY_OVERLAP,
    numeric_divergence: float = DEFAULT_NUMERIC_DIVERGENCE,
    percent_divergence: float = DEFAULT_PERCENT_DIVERGENCE,
) -> list[dict]:
    """Compare each new finding against history. Return contradiction records."""
    contradictions: list[dict] = []
    for new in new_findings:
        new_entities = _entity_set(new)
        if not new_entities:
            continue
        for old in history:
            if _same_finding(new, old):
                continue
            if new.get("category") != old.get("category"):
                continue
            if _domain(new) == _domain(old):
                continue
            old_entities = _entity_set(old)
            if not old_entities:
                continue
            jaccard = _jaccard(new_entities, old_entities)
            if jaccard < entity_overlap:
                continue
            verdict = _compare(new, old, numeric_divergence, percent_divergence)
            if verdict is None:
                continue
            contradictions.append(
                {
                    "src_hash": _hash(new),
                    "dst_hash": _hash(old),
                    "src_title": new.get("title", ""),
                    "dst_title": old.get("title", ""),
                    "src_date": new.get("date_observed", "unknown"),
                    "dst_date": old.get("date_observed", "unknown"),
                    "src_source": new.get("source_name", ""),
                    "dst_source": old.get("source_name", ""),
                    "category": new.get("category", ""),
                    "entity_overlap": round(jaccard, 3),
                    "kind": verdict["kind"],
                    "rationale": verdict["rationale"],
                    "confidence": verdict["confidence"],
                    "detected_at": datetime.now(timezone.utc).isoformat(),
                }
            )
    return contradictions


# --- candidate comparison ---


def _compare(
    new: dict,
    old: dict,
    numeric_divergence: float,
    percent_divergence: float,
) -> dict | None:
    """Return the strongest disagreement signal, or None."""
    new_text = _text(new)
    old_text = _text(old)

    # Order matters. Directional disagreement is a cleaner signal than weak
    # numeric divergence (Pattern 6 — keep alerts cheap and precise). Numeric
    # checks come second and only fire when no value is shared between sides.

    # 1. Directional disagreement (rise / fall / stable).
    new_dir = _directions(new_text)
    old_dir = _directions(old_text)
    if new_dir and old_dir and _directions_disagree(new_dir, old_dir):
        return {
            "kind": "directional",
            "rationale": (
                f"directional disagreement: {sorted(new_dir)} vs {sorted(old_dir)}"
            ),
            "confidence": 0.7,
        }

    # 2. Agreement / negation flips.
    flip = _negation_flip(new_text, old_text)
    if flip:
        return {
            "kind": "negation",
            "rationale": flip,
            "confidence": 0.75,
        }

    # 3. Numeric magnitude divergence (prices in same currency). Skip when both
    # sides report the same value — that's corroboration, not contradiction.
    new_dollars = _dollars(new_text)
    old_dollars = _dollars(old_text)
    if new_dollars and old_dollars and not _values_agree(new_dollars, old_dollars):
        spread = max(*new_dollars, *old_dollars) / max(min(*new_dollars, *old_dollars), 0.01)
        if spread >= numeric_divergence:
            return {
                "kind": "numeric_divergence",
                "rationale": (
                    f"shared entities but ${min(*new_dollars, *old_dollars):.2f} vs "
                    f"${max(*new_dollars, *old_dollars):.2f} (×{spread:.2f})"
                ),
                "confidence": min(0.95, 0.45 + 0.25 * (spread - numeric_divergence)),
            }

    # 4. Percentage-point divergence — same rule, but require no shared value.
    new_pcts = _percents(new_text)
    old_pcts = _percents(old_text)
    if new_pcts and old_pcts and not _values_agree(new_pcts, old_pcts):
        gap = abs(max(new_pcts) - min(old_pcts))
        if gap >= percent_divergence:
            return {
                "kind": "percent_divergence",
                "rationale": (
                    f"shared entities but {min(old_pcts):.1f}% vs "
                    f"{max(new_pcts):.1f}% ({gap:.1f}pp gap)"
                ),
                "confidence": min(0.85, 0.4 + 0.05 * gap),
            }

    return None


def _values_agree(a: list[float], b: list[float], tolerance: float = 0.05) -> bool:
    """True when any value in a matches any value in b within `tolerance` (relative)."""
    for x in a:
        for y in b:
            base = max(abs(x), abs(y), 1e-6)
            if abs(x - y) / base <= tolerance:
                return True
    return False


# --- extraction helpers ---


def _entity_set(finding: dict) -> set[str]:
    raw = finding.get("key_entities") or []
    if isinstance(raw, list) and raw:
        return {str(e).strip().lower() for e in raw if e}
    # Fallback: pull capitalised tokens from title + details.
    text = _text(finding)
    return {w.lower() for w in re.findall(r"[A-Z][A-Za-z]{3,}", text)}


def _text(finding: dict) -> str:
    return f"{finding.get('title', '')} {finding.get('details', '')}"


def _domain(finding: dict) -> str:
    d = finding.get("source_domain")
    if d:
        return d
    url = finding.get("source_url", "")
    return url.split("//", 1)[-1].split("/", 1)[0].removeprefix("www.")


def _hash(finding: dict) -> str:
    return finding.get("content_hash") or finding.get("_content_hash") or ""


def _same_finding(a: dict, b: dict) -> bool:
    ha, hb = _hash(a), _hash(b)
    if ha and hb:
        return ha == hb
    return a.get("source_url") == b.get("source_url") and a.get("title") == b.get("title")


def _dollars(text: str) -> list[float]:
    out: list[float] = []
    for raw in RE_DOLLAR.findall(text):
        n = _parse_number(raw)
        if n is not None:
            out.append(n)
    return out


def _percents(text: str) -> list[float]:
    out: list[float] = []
    for raw in RE_PERCENT.findall(text):
        n = _parse_number(raw)
        if n is not None:
            out.append(n)
    return out


def _directions(text: str) -> set[str]:
    words = {w.lower() for w in RE_WORDS.findall(text)}
    found = set()
    if words & DIRECTION_RISE:
        found.add("rise")
    if words & DIRECTION_FALL:
        found.add("fall")
    if words & DIRECTION_STABLE:
        found.add("stable")
    return found


def _directions_disagree(a: set[str], b: set[str]) -> bool:
    if not a or not b or a == b:
        return False
    incompatible = {
        frozenset({"rise", "fall"}),
        frozenset({"rise", "stable"}),
        frozenset({"fall", "stable"}),
    }
    union = frozenset(a | b)
    return union in incompatible or any(
        frozenset({x, y}) in incompatible for x in a for y in b if x != y
    )


def _negation_flip(text_a: str, text_b: str) -> str | None:
    words_a = {w.lower() for w in RE_WORDS.findall(text_a)}
    words_b = {w.lower() for w in RE_WORDS.findall(text_b)}
    for positive, negative in NEGATION_AGREEMENT_PAIRS:
        a_pos = words_a & positive
        a_neg = words_a & negative
        b_pos = words_b & positive
        b_neg = words_b & negative
        if (a_pos and b_neg) or (a_neg and b_pos):
            return (
                f"agreement/negation flip: {sorted(a_pos | a_neg)} vs "
                f"{sorted(b_pos | b_neg)}"
            )
    return None


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


# --- CLI: backfill over existing history ---


def main(argv: Iterable[str] | None = None) -> int:
    import argparse

    from research.config import load_config, resolve_path
    from research.store import WorkspaceStore

    parser = argparse.ArgumentParser(
        description="Detect contradictions between findings already in history.",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=90,
        help="History window to scan (default: 90 days).",
    )
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="Print contradictions but do not append to contradictions.jsonl.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    config = load_config()
    store = WorkspaceStore(
        history_path=resolve_path(config, "history"),
        index_path=resolve_path(config, "dedup_index"),
    )
    history = store.load_history(max_age_days=args.lookback_days)
    log.info(f"Scanning {len(history)} findings for contradictions...")

    # Compare every finding against everything dated earlier.
    history_sorted = sorted(history, key=lambda f: f.get("date_observed", ""))
    contradictions: list[dict] = []
    for i, new in enumerate(history_sorted):
        prior = history_sorted[:i]
        contradictions.extend(detect_contradictions([new], prior))

    log.info(f"Detected {len(contradictions)} contradictions.")
    for c in contradictions:
        log.info(
            f"  [{c['kind']}] '{c['src_title'][:60]}' vs "
            f"'{c['dst_title'][:60]}' — {c['rationale']} (conf {c['confidence']:.2f})"
        )

    if not args.print_only and contradictions:
        store.append_contradictions(contradictions)
        log.info(f"Appended to {store.contradictions_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

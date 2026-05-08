"""Daily briefing — the interpreter surface for the workspace.

Maps to:
    Pattern 7  (Interpreter as synthesis, not command)
    Pattern 8  (Anti-confabulation envelope — coverage, gaps, confidence)
    Pattern 10 (Salience as workflow)
    Pattern 18 (Progressive disclosure)
    §7.1       (Briefing flow)

The briefing reads the substrate and renders sections to stdout (or a markdown
file). It NEVER writes to history, NEVER writes to findings.md, NEVER mutates
the dedup index. The accountability boundary (§13) holds: this is a read-only
synthesis surface; the human decides what to do.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

from research.config import load_config, resolve_path
from research.constants import (
    DEFAULT_HISTORY_LOOKBACK_DAYS,
    DEFAULT_MIN_COMPOSITE_SCORE,
    TIER_THRESHOLDS,
)
from research.contradictions import detect_contradictions
from research.salience import (
    SalienceBreakdown,
    load_salience_config,
    rank_findings,
)
from research.store import WorkspaceStore

log = logging.getLogger(__name__)


# --- main entry point ---


def main(argv: Iterable[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(
        description="Render today's research briefing from the substrate.",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=DEFAULT_HISTORY_LOOKBACK_DAYS,
        help="History window for stale checks and corroboration (default: 30).",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Maximum items per section (default: 10).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write the briefing to this markdown path instead of stdout.",
    )
    parser.add_argument(
        "--today",
        default=None,
        help="Override 'today' as YYYY-MM-DD (useful for tests).",
    )
    parser.add_argument(
        "--detect-contradictions",
        action="store_true",
        help="Run a fresh contradiction sweep before rendering.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    config = load_config()
    today = args.today or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    store = WorkspaceStore(
        history_path=resolve_path(config, "history"),
        index_path=resolve_path(config, "dedup_index"),
    )

    text = render_briefing(
        store,
        config=config,
        today=today,
        lookback_days=args.lookback_days,
        top=args.top,
        run_fresh_contradictions=args.detect_contradictions,
    )

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text)
        log.info(f"Wrote briefing to {args.out}")
    else:
        sys.stdout.write(text)
    return 0


# --- rendering ---


def render_briefing(
    store: WorkspaceStore,
    *,
    config: dict,
    today: str,
    lookback_days: int = DEFAULT_HISTORY_LOOKBACK_DAYS,
    top: int = 10,
    run_fresh_contradictions: bool = False,
) -> str:
    all_history = store.load_history()
    recent_history = _within_lookback(all_history, today, lookback_days)

    # If asked, recompute contradictions over all history.
    if run_fresh_contradictions:
        fresh = []
        sorted_hist = sorted(all_history, key=lambda f: f.get("date_observed", ""))
        for i, f in enumerate(sorted_hist):
            fresh.extend(detect_contradictions([f], sorted_hist[:i]))
        if fresh:
            store.append_contradictions(fresh)

    contradictions = store.load_contradictions()
    feedback = store.feedback_by_hash()

    # Index contradictions per finding hash (both sides).
    contradictions_by_hash: dict[str, list[dict]] = defaultdict(list)
    for c in contradictions:
        contradictions_by_hash[c.get("src_hash", "")].append(c)
        contradictions_by_hash[c.get("dst_hash", "")].append(c)

    # Cross-language corroborator detection runs over all history.
    cross_lang_hashes = _cross_language_corroborated(all_history)

    salience_cfg = load_salience_config()
    # Rank everything we know — the lookback is a per-section concern, not a
    # global filter. Stale-review items are by definition outside the window.
    ranked_all = rank_findings(
        all_history,
        config=salience_cfg,
        contradictions_for_hash=contradictions_by_hash,
        feedback_for_hash=feedback,
        cross_language_hashes=cross_lang_hashes,
        today=today,
    )
    recent_hashes = {
        (f.get("content_hash") or f.get("_content_hash") or "")
        for f in recent_history
    }
    ranked_recent = [
        (f, sb)
        for f, sb in ranked_all
        if (f.get("content_hash") or f.get("_content_hash") or "") in recent_hashes
    ]

    # --- assemble sections ---

    new_today = [(f, sb) for f, sb in ranked_recent if f.get("date_observed") == today]
    verified = [
        (f, sb) for f, sb in ranked_recent
        if f.get("composite_score", 0) >= TIER_THRESHOLDS["Verified"]
    ][:top]
    likely = [
        (f, sb) for f, sb in ranked_recent
        if TIER_THRESHOLDS["Likely"] <= f.get("composite_score", 0) < TIER_THRESHOLDS["Verified"]
    ][:top]

    open_contradictions = sorted(
        contradictions, key=lambda c: c.get("detected_at", ""), reverse=True
    )[:top]

    # Stale/overdue uses the full history — that's the whole point.
    stale_overdue = [
        (f, sb)
        for f, sb in ranked_all
        if sb.components.get("stale_review_overdue", 0) >= 0.5
    ][:top]

    coverage = _coverage_breakdown(recent_history, config, lookback_days, today)
    confidence = _confidence_assessment(ranked_recent, contradictions, coverage)

    # --- render markdown ---

    lines: list[str] = []
    lines.append(f"# Research Briefing — {today}")
    lines.append("")
    lines.append(_headline(new_today, open_contradictions, stale_overdue))
    lines.append("")

    _section(lines, f"## New today ({len(new_today)})", new_today)
    _section(lines, f"## Verified tier ({len(verified)})", verified)
    _section(lines, f"## Likely tier ({len(likely)})", likely)
    _contradictions_section(lines, open_contradictions)
    _section(lines, f"## Stale or review-overdue ({len(stale_overdue)})", stale_overdue)

    lines.append("## Coverage")
    lines.append("")
    for category, count in sorted(coverage["by_category"].items(), key=lambda kv: -kv[1]):
        lines.append(f"- {category}: {count}")
    if coverage["empty_categories"]:
        lines.append("")
        lines.append("Categories with zero findings in window:")
        for cat in coverage["empty_categories"]:
            lines.append(f"- {cat}")
    lines.append("")
    lines.append("By language:")
    for lang, count in sorted(coverage["by_language"].items(), key=lambda kv: -kv[1]):
        lines.append(f"- {lang}: {count}")
    lines.append("")

    # Anti-confabulation envelope (Pattern 8).
    lines.append("## Anti-confabulation envelope")
    lines.append("")
    lines.append(f"- **Checked:** {coverage['n_findings']} findings in last "
                 f"{lookback_days} days, {len(coverage['by_category'])} categories, "
                 f"{len(coverage['by_language'])} languages.")
    lines.append(f"- **Total stored history:** {len(all_history)} findings.")
    lines.append(f"- **Stale or overdue:** {len(stale_overdue)}")
    lines.append(f"- **Open contradictions:** {len(contradictions)}")
    if coverage["empty_categories"]:
        lines.append(
            f"- **Missing:** {len(coverage['empty_categories'])} categories had "
            f"no findings in window — {', '.join(coverage['empty_categories'])}."
        )
    lines.append(f"- **Confidence:** {confidence}")
    lines.append("- **Tool actions taken:** none (read-only synthesis).")
    lines.append("")

    return "\n".join(lines) + "\n"


# --- section renderers ---


def _headline(new_today, open_contradictions, stale_overdue) -> str:
    parts: list[str] = []
    if new_today:
        f, _ = new_today[0]
        parts.append(f"**{len(new_today)} new today.** Top: {f.get('title', '')[:90]}")
    else:
        parts.append("No new findings dated today.")
    if open_contradictions:
        c = open_contradictions[0]
        parts.append(
            f"**Top contradiction:** [{c.get('kind', '')}] "
            f"{c.get('src_title', '')[:60]} ⇄ {c.get('dst_title', '')[:60]}"
        )
    if stale_overdue:
        f, _ = stale_overdue[0]
        parts.append(f"**Top stale claim:** {f.get('title', '')[:90]}")
    return "\n\n".join(f"> {p}" for p in parts)


def _section(lines: list[str], title: str, items: list[tuple[dict, SalienceBreakdown]]) -> None:
    lines.append(title)
    lines.append("")
    if not items:
        lines.append("_(none)_")
        lines.append("")
        return
    for f, sb in items:
        lines.append(f"### {f.get('title', 'Untitled')}")
        lines.append(
            f"- **Salience:** {sb.score:.2f} — {', '.join(sb.reasons) if sb.reasons else 'baseline'}"
        )
        lines.append(f"- **Breakdown:** {sb.explain()}")
        lines.append(
            f"- **Quality:** {f.get('quality_tier', '?')} "
            f"({f.get('composite_score', 0)}/5.0) — {f.get('source_name', '?')} "
            f"({f.get('source_language', '?')})"
        )
        lines.append(
            f"- **Date observed:** {f.get('date_observed', 'unknown')}  "
            f"**Category:** {f.get('category', '?')}"
        )
        if f.get("source_url"):
            lines.append(f"- {f['source_url']}")
        lines.append("")


def _contradictions_section(lines: list[str], items: list[dict]) -> None:
    lines.append(f"## Open contradictions ({len(items)})")
    lines.append("")
    if not items:
        lines.append("_(none)_")
        lines.append("")
        return
    for c in items:
        lines.append(
            f"### [{c.get('kind', '?')}] {c.get('src_title', '')[:80]}"
        )
        lines.append(
            f"- **Vs prior claim:** {c.get('dst_title', '')[:120]}"
        )
        lines.append(
            f"- **Rationale:** {c.get('rationale', '?')}"
        )
        lines.append(
            f"- **Sources:** {c.get('src_source', '?')} ({c.get('src_date', '?')}) "
            f"vs {c.get('dst_source', '?')} ({c.get('dst_date', '?')})"
        )
        lines.append(
            f"- **Confidence:** {c.get('confidence', 0):.2f}  "
            f"**Entity overlap:** {c.get('entity_overlap', 0):.2f}"
        )
        lines.append("")


# --- coverage and confidence ---


def _coverage_breakdown(
    history: list[dict], config: dict, lookback_days: int, today: str
) -> dict:
    config_categories = [c.get("name", "") for c in config.get("categories", [])]
    by_category = Counter(f.get("category", "Uncategorized") for f in history)
    by_language = Counter(f.get("source_language", "?") for f in history)
    empty = sorted(c for c in config_categories if c and c not in by_category)
    return {
        "n_findings": len(history),
        "by_category": dict(by_category),
        "by_language": dict(by_language),
        "empty_categories": empty,
        "lookback_days": lookback_days,
    }


def _confidence_assessment(
    ranked: list[tuple[dict, SalienceBreakdown]],
    contradictions: list[dict],
    coverage: dict,
) -> str:
    """Return a short qualifier explaining how much to trust this briefing."""
    n = coverage["n_findings"]
    if n == 0:
        return "very low — no findings in window."
    verified = sum(
        1
        for f, _ in ranked
        if f.get("composite_score", 0) >= TIER_THRESHOLDS["Verified"]
    )
    pct_verified = verified / n
    parts: list[str] = []
    if pct_verified >= 0.4:
        parts.append("high")
    elif pct_verified >= 0.2:
        parts.append("moderate")
    else:
        parts.append("low")
    if coverage["empty_categories"]:
        parts.append(f"({len(coverage['empty_categories'])} blind categories)")
    if contradictions:
        parts.append(f"({len(contradictions)} open contradictions)")
    return " ".join(parts)


# --- cross-language corroboration ---


def _cross_language_corroborated(history: list[dict]) -> set[str]:
    """Return hashes of findings that share entities + category with at least one
    finding from a different language."""
    by_category: dict[str, list[dict]] = defaultdict(list)
    for f in history:
        by_category[f.get("category", "")].append(f)
    out: set[str] = set()
    for cat_findings in by_category.values():
        if len(cat_findings) < 2:
            continue
        for i, a in enumerate(cat_findings):
            ea = set(a.get("key_entities") or [])
            if not ea:
                continue
            for b in cat_findings[i + 1 :]:
                if a.get("source_language") == b.get("source_language"):
                    continue
                eb = set(b.get("key_entities") or [])
                if not eb:
                    continue
                inter = len(ea & eb)
                union = len(ea | eb)
                if union and inter / union >= 0.30:
                    out.add(a.get("content_hash") or a.get("_content_hash") or "")
                    out.add(b.get("content_hash") or b.get("_content_hash") or "")
    return out


def _within_lookback(findings: list[dict], today: str, lookback_days: int) -> list[dict]:
    """Filter findings whose date_observed is within `lookback_days` of `today`.

    Findings with date_observed='unknown' pass through (they may still be useful).
    """
    from datetime import timedelta

    today_d = datetime.strptime(today, "%Y-%m-%d").date()
    cutoff = (today_d - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    out: list[dict] = []
    for f in findings:
        d = f.get("date_observed", "unknown")
        if d == "unknown" or d >= cutoff:
            out.append(f)
    return out


def _iter_unique_findings(findings: Iterable[dict]) -> Iterator[dict]:
    seen: set[str] = set()
    for f in findings:
        h = f.get("content_hash") or f.get("_content_hash") or ""
        if h in seen:
            continue
        seen.add(h)
        yield f


if __name__ == "__main__":
    sys.exit(main())

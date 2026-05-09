"""Main orchestrator: runs one complete research cycle."""

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from research.config import load_config, resolve_path
from research.searcher import search_category
from research.analyzer import analyze_results
from research.scorer import load_authority_db, load_history, save_history, score_findings
from research.dedup import load_index, save_index, deduplicate
from research.logger import append_findings, write_run_log
from research.contradictions import detect_contradictions
from research.store import WorkspaceStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


def select_categories(config: dict) -> list[dict]:
    """Select a subset of categories for this run using rotation."""
    categories = config["categories"]
    schedule = config.get("schedule", {})
    rotate = schedule.get("rotate_categories", True)

    if not rotate:
        return categories

    # Deterministic rotation based on day-of-year and hour
    now = datetime.now(timezone.utc)
    run_index = now.timetuple().tm_yday * 24 + now.hour
    cats_per_run = max(1, (len(categories) + 1) // 2)  # ~half the categories per run

    start = run_index % len(categories)
    selected = []
    for i in range(cats_per_run):
        idx = (start + i) % len(categories)
        selected.append(categories[idx])

    return selected


def check_ollama(config: dict) -> bool:
    """Verify Ollama is reachable and model is available."""
    import ollama
    try:
        client = ollama.Client(host=config.get("ollama_url", "http://localhost:11434"))
        models = client.list()
        model_names = [m.model for m in models.models]
        target = config["model"]
        # Check if target model is available (allow partial match)
        for name in model_names:
            if target in name or name.startswith(target):
                return True
        log.error(f"Model '{target}' not found. Available: {model_names}")
        return False
    except Exception as e:
        log.error(f"Cannot reach Ollama: {e}")
        return False


def _extract_domain_simple(url: str) -> str:
    """Quick domain extraction for stats logging."""
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc.removeprefix("www.") or "unknown"
    except Exception:
        return "unknown"


def check_external_drive() -> bool:
    """Verify the external drive is mounted."""
    if not Path("/Volumes/OWC Envoy Ultra").exists():
        log.error("External drive not mounted at /Volumes/OWC Envoy Ultra")
        return False
    return True


def run():
    """Execute one research cycle."""
    log.info("=" * 60)
    log.info("Research Agent starting")
    log.info("=" * 60)

    config = load_config()
    findings_path = resolve_path(config, "findings")
    index_path = resolve_path(config, "dedup_index")
    log_dir = resolve_path(config, "log_dir")

    # Scoring config
    scoring_config = config.get("scoring", {})
    project_root = Path(__file__).resolve().parent.parent
    authority_db_path = project_root / scoring_config.get("authority_db", "configs/source-authority.yaml")
    history_path = project_root / scoring_config.get("history_file", "data/findings_history.json")
    min_score = scoring_config.get("min_composite_score", 2.0)
    lookback_days = scoring_config.get("history_lookback_days", 30)
    score_weights = scoring_config.get("weights", None)

    stats = {
        "categories_searched": 0,
        "queries_executed": 0,
        "search_results": 0,
        "findings_extracted": 0,
        "findings_rejected": 0,
        "duplicates_skipped": 0,
        "new_findings": 0,
        "contradictions_detected": 0,
        "errors": 0,
        "avg_composite_score": 0.0,
        "tier_counts": {"Verified": 0, "Likely": 0, "Unverified": 0, "Unreliable": 0},
        "rejected_findings": [],
    }

    # Pre-flight checks
    if not check_external_drive():
        log.warning("External drive not mounted — continuing anyway (model may be cached)")

    if not check_ollama(config):
        log.error("Ollama pre-flight check failed. Aborting.")
        write_run_log(log_dir, stats)
        return 1

    # Select categories for this run
    categories = select_categories(config)
    languages = config["languages"]
    stats["categories_searched"] = len(categories)

    log.info(f"Searching {len(categories)} categories: {[c['name'] for c in categories]}")
    log.info(f"Languages: {[l['code'] for l in languages]}")

    # Search phase
    all_search_results = []
    for cat in categories:
        log.info(f"\nSearching: {cat['name']}")
        results = search_category(cat, languages, config)
        all_search_results.extend(results)

    stats["search_results"] = len(all_search_results)
    # Count queries executed
    for cat in categories:
        for lang in languages:
            stats["queries_executed"] += len(cat.get("queries", {}).get(lang["code"], []))

    log.info(f"\nTotal search results: {len(all_search_results)}")

    if not all_search_results:
        log.warning("No search results found. Nothing to analyze.")
        write_run_log(log_dir, stats)
        return 0

    # Analysis phase
    log.info("\nAnalyzing results with LLM...")
    findings = analyze_results(all_search_results, config)
    stats["findings_extracted"] = len(findings)

    # Scoring phase
    log.info("\nScoring findings...")
    authority_db = load_authority_db(authority_db_path)
    history = load_history(history_path, max_age_days=lookback_days)
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    score_findings(findings, authority_db, history, run_date, weights=score_weights)

    # Compute scoring stats
    if findings:
        scores = [f.get("composite_score", 0) for f in findings]
        stats["avg_composite_score"] = round(sum(scores) / len(scores), 2)
        for f in findings:
            tier = f.get("quality_tier", "Unreliable")
            stats["tier_counts"][tier] = stats["tier_counts"].get(tier, 0) + 1

    # Filter out unreliable findings
    accepted = [f for f in findings if f.get("composite_score", 0) >= min_score]
    rejected = [f for f in findings if f.get("composite_score", 0) < min_score]
    stats["findings_rejected"] = len(rejected)
    stats["rejected_findings"] = [
        {"title": f.get("title", "")[:80], "score": f.get("composite_score", 0),
         "source": _extract_domain_simple(f.get("source_url", ""))}
        for f in rejected
    ]
    log.info(f"  Accepted: {len(accepted)}, Rejected (score < {min_score}): {len(rejected)}")

    # Dedup phase
    log.info("\nDeduplicating...")
    index = load_index(index_path)
    index_size_before = len(index)
    new_findings = deduplicate(accepted, index)
    stats["duplicates_skipped"] = len(accepted) - len(new_findings)
    stats["new_findings"] = len(new_findings)
    save_index(index, index_path)

    # Contradiction detection (Pattern 6 — structural alert propagation).
    # Compare each new finding against the recent history that drove
    # corroboration scoring. The store appends contradictions append-only;
    # the human reviews them via the briefing.
    if new_findings:
        contradictions = detect_contradictions(new_findings, history)
        if contradictions:
            store = WorkspaceStore(
                history_path=history_path,
                index_path=index_path,
            )
            store.append_contradictions(contradictions)
            stats["contradictions_detected"] = len(contradictions)
            log.info(
                f"  Detected {len(contradictions)} possible contradiction(s) "
                f"-- review with `python -m research.brief`."
            )

    # Save to history
    save_history(history_path, history, new_findings)

    # Logging phase
    log.info("\nLogging findings...")
    append_findings(new_findings, findings_path)
    write_run_log(log_dir, stats)

    log.info("\n" + "=" * 60)
    log.info(f"Run complete. {stats['new_findings']} new findings logged.")
    log.info(f"Scoring: avg={stats['avg_composite_score']}, "
             f"Verified={stats['tier_counts']['Verified']}, "
             f"Likely={stats['tier_counts']['Likely']}, "
             f"Unverified={stats['tier_counts']['Unverified']}, "
             f"Unreliable={stats['tier_counts']['Unreliable']}")
    log.info(f"Dedup index: {index_size_before} -> {len(index)} entries")
    log.info("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(run())

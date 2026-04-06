"""Deduplication using content hashing."""

import hashlib
import json
import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)


def load_index(index_path: Path) -> dict:
    """Load the dedup index from disk."""
    if index_path.exists():
        with open(index_path) as f:
            return json.load(f)
    return {}


def save_index(index: dict, index_path: Path):
    """Save the dedup index to disk."""
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with open(index_path, "w") as f:
        json.dump(index, f, indent=2)


def deduplicate(findings: list[dict], index: dict) -> list[dict]:
    """Filter out findings already in the index. Returns new findings only."""
    new_findings = []
    for finding in findings:
        content_hash = _hash_finding(finding)
        if content_hash in index:
            log.debug(f"  Duplicate skipped: {finding.get('title', '')[:60]}")
            continue
        index[content_hash] = {
            "title": finding.get("title", ""),
            "first_seen": finding.get("date_observed", "unknown"),
            "source_url": finding.get("source_url", ""),
            "composite_score": finding.get("composite_score"),
            "category": finding.get("category", ""),
        }
        finding["_content_hash"] = content_hash
        new_findings.append(finding)

    dupes = len(findings) - len(new_findings)
    log.info(f"  Dedup: {len(new_findings)} new, {dupes} duplicates skipped")
    return new_findings


def _hash_finding(finding: dict) -> str:
    """Create a normalized hash of a finding's core content."""
    # Combine title + details + source_url for the hash
    raw = " ".join([
        finding.get("title", ""),
        finding.get("details", ""),
        finding.get("source_url", ""),
    ])
    # Normalize: lowercase, strip extra whitespace and punctuation
    normalized = re.sub(r"[^\w\s]", "", raw.lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]

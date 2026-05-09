"""Thin store abstraction over the existing JSON files.

Phase 1: a stable interface around findings_history.json, findings_index.json,
contradictions.jsonl, and feedback.jsonl. Phase 2 swaps the backend to SQLite
without touching callers.

Design rule (Pattern 1 — Substrate-Routine Split):
    The store enforces structure, identity, and persistence.
    It MUST NOT compute salience, decide what's a contradiction, or rank items.
    Routines do that and write the result back through the store.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

log = logging.getLogger(__name__)


class WorkspaceStore:
    """JSON-backed substrate. Phase 2 will replace this with SQLite."""

    def __init__(
        self,
        history_path: Path,
        index_path: Path,
        contradictions_path: Path | None = None,
        feedback_path: Path | None = None,
    ):
        self.history_path = Path(history_path)
        self.index_path = Path(index_path)
        self.contradictions_path = (
            Path(contradictions_path)
            if contradictions_path
            else self.history_path.parent / "contradictions.jsonl"
        )
        self.feedback_path = (
            Path(feedback_path)
            if feedback_path
            else self.history_path.parent / "feedback.jsonl"
        )

    # --- findings history (becomes `items` in Phase 2) ---

    def load_history(self, max_age_days: int | None = None) -> list[dict]:
        if not self.history_path.exists():
            return []
        try:
            with open(self.history_path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            log.warning(f"Failed to load history: {e}")
            return []

        findings = data.get("findings", [])
        if max_age_days is None:
            return findings

        from datetime import timedelta

        cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).strftime("%Y-%m-%d")
        return [
            f
            for f in findings
            if f.get("date_observed", "unknown") >= cutoff
            or f.get("date_observed") == "unknown"
        ]

    def save_history(self, history: list[dict]) -> None:
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "findings": history,
            "meta": {
                "total_findings": len(history),
                "last_updated": datetime.now(timezone.utc).isoformat(),
            },
        }
        with open(self.history_path, "w") as f:
            json.dump(data, f, indent=2)

    # --- dedup index ---

    def load_index(self) -> dict:
        if not self.index_path.exists():
            return {}
        with open(self.index_path) as f:
            return json.load(f)

    def save_index(self, index: dict) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.index_path, "w") as f:
            json.dump(index, f, indent=2)

    # --- contradictions (becomes `links` of type `contradicts` in Phase 2) ---

    def append_contradictions(self, contradictions: Iterable[dict]) -> int:
        self.contradictions_path.parent.mkdir(parents=True, exist_ok=True)
        n = 0
        with open(self.contradictions_path, "a") as f:
            for c in contradictions:
                f.write(json.dumps(c, sort_keys=True) + "\n")
                n += 1
        return n

    def load_contradictions(self) -> list[dict]:
        if not self.contradictions_path.exists():
            return []
        out: list[dict] = []
        with open(self.contradictions_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    log.warning(f"Skipping malformed contradiction line: {line[:80]}")
        return out

    # --- feedback (becomes `feedback` table in Phase 2) ---

    def append_feedback(self, content_hash: str, feedback: str, note: str = "") -> dict:
        self.feedback_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "content_hash": content_hash,
            "feedback": feedback,
            "note": note,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(self.feedback_path, "a") as f:
            f.write(json.dumps(record, sort_keys=True) + "\n")
        return record

    def load_feedback(self) -> list[dict]:
        if not self.feedback_path.exists():
            return []
        out: list[dict] = []
        with open(self.feedback_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return out

    def feedback_by_hash(self) -> dict[str, list[dict]]:
        """Group feedback by content_hash, latest last."""
        by_hash: dict[str, list[dict]] = {}
        for r in self.load_feedback():
            by_hash.setdefault(r.get("content_hash", ""), []).append(r)
        return by_hash

    # --- iteration helper ---

    def iter_history(self) -> Iterator[dict]:
        yield from self.load_history()

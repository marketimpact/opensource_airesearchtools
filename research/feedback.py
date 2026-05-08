"""Lightweight feedback CLI (Pattern 20 — feedback-tuned attention).

Records `useful | noise | snoozed | pinned | resolved` against a finding's
content_hash. The briefing salience workflow reads this back. Feedback is
append-only — never destructive — so the audit trail survives.
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Iterable

from research.config import load_config, resolve_path
from research.store import WorkspaceStore

VALID_FEEDBACK = {"useful", "noise", "snoozed", "pinned", "resolved"}

log = logging.getLogger(__name__)


def main(argv: Iterable[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(
        description="Mark a finding useful / noise / snoozed / pinned / resolved.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    add = sub.add_parser("add", help="Record feedback against a finding.")
    add.add_argument("content_hash")
    add.add_argument("feedback", choices=sorted(VALID_FEEDBACK))
    add.add_argument("--note", default="")

    listcmd = sub.add_parser("list", help="List recent feedback.")
    listcmd.add_argument("--limit", type=int, default=20)

    show = sub.add_parser("show", help="Show feedback for one finding.")
    show.add_argument("content_hash")

    args = parser.parse_args(list(argv) if argv is not None else None)

    config = load_config()
    store = WorkspaceStore(
        history_path=resolve_path(config, "history"),
        index_path=resolve_path(config, "dedup_index"),
    )

    if args.cmd == "add":
        record = store.append_feedback(args.content_hash, args.feedback, args.note)
        log.info(f"Recorded: {record}")
        # Confirm the finding actually exists; warn but don't error.
        history = store.load_history()
        if not any(
            (f.get("content_hash") or f.get("_content_hash")) == args.content_hash
            for f in history
        ):
            log.warning(
                f"  Note: no finding with hash {args.content_hash!r} in history. "
                "Feedback recorded anyway (it may match a future finding)."
            )
        return 0

    if args.cmd == "list":
        records = store.load_feedback()[-args.limit :]
        if not records:
            log.info("No feedback recorded yet.")
            return 0
        for r in records:
            log.info(
                f"  {r.get('created_at', '')}  {r.get('feedback', ''):8}  "
                f"{r.get('content_hash', '')}  {r.get('note', '')}"
            )
        return 0

    if args.cmd == "show":
        grouped = store.feedback_by_hash().get(args.content_hash, [])
        if not grouped:
            log.info(f"No feedback for {args.content_hash}.")
            return 0
        for r in grouped:
            log.info(
                f"  {r.get('created_at', '')}  {r.get('feedback', ''):8}  "
                f"{r.get('note', '')}"
            )
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())

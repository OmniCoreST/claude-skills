#!/usr/bin/env python3
"""Claude Code hook: carries sent feedback into the agent's context.

Wired to three events, each answering a different "when would the agent
otherwise miss this?":

  SessionStart      - you come back tomorrow; unfinished items are still there.
  UserPromptSubmit  - you send while the agent is idle; it arrives with your
                      next message instead of waiting to be asked about.
  Stop              - you send while the agent is mid-task; exit 2 keeps the
                      turn alive so the fix happens now rather than after you
                      notice nothing happened and prod it.

Termination is guaranteed by the store, not by this script: `take_undelivered`
claims and stamps in one locked write, so an item can block Stop exactly once.
A hook that could re-serve the same batch would trap the session in a loop.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from render import brief, summarize  # noqa: E402
from store import DIR_NAME, Store, find_project_root  # noqa: E402

CLI = Path(__file__).resolve().parent / "uifb.py"


def plural(n: int) -> tuple[str, str]:
    """(suffix, verb) so the briefing reads as English at any count."""
    return ("s", "were") if n != 1 else ("", "was")


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}

    event = payload.get("hook_event_name") or ""
    root = find_project_root(payload.get("cwd") or os.getcwd())
    data_dir = root / DIR_NAME

    # Never speak in a project that has not opted in - a stray hook firing in
    # unrelated repos is how people learn to delete hooks.
    if not (data_dir / "feedback.json").exists():
        return 0

    store = Store(data_dir)

    if event == "Stop":
        return on_stop(store, data_dir)
    if event == "UserPromptSubmit":
        return emit_context(store, data_dir, event, include_summary=False)
    if event == "SessionStart":
        return emit_context(store, data_dir, event, include_summary=True)
    return 0


def on_stop(store: Store, data_dir: Path) -> int:
    items = store.take_undelivered()
    if not items:
        return 0
    suffix, _ = plural(len(items))
    text = brief(
        items, data_dir, CLI,
        header=f"The reviewer just sent {len(items)} UI feedback item{suffix} from the "
               "review rail. Work through them now, before ending the turn.",
    )
    # Exit 2 is the documented way to keep a Stop from landing; stderr is what
    # gets handed back as the reason.
    sys.stderr.write(text + "\n")
    return 2


def emit_context(store: Store, data_dir: Path, event: str, *, include_summary: bool) -> int:
    items = store.take_undelivered()
    chunks: list[str] = []

    if include_summary:
        counts = store.counts()
        if any(counts.get(k) for k in ("open", "sent", "in_progress")):
            chunks.append(f"UI feedback ledger ({data_dir}): {summarize(counts)}.")

        # A fresh session has no memory of what an earlier one was handed, so
        # re-brief anything still open in full. Carrying only a count would
        # leave the agent knowing work exists but not what it is - which is how
        # unfinished items quietly become abandoned ones.
        claimed = {i["id"] for i in items}
        carried = [
            i for i in store.read()["items"]
            if i.get("status") in ("sent", "in_progress") and i["id"] not in claimed
        ]
        if carried:
            in_flight = sum(1 for i in carried if i.get("status") == "in_progress")
            many = len(carried) != 1
            header = (f"{len(carried)} UI feedback item{'s' if many else ''} from earlier "
                      f"{'are' if many else 'is'} still open.")
            if in_flight:
                header += (" Some were already claimed by an interrupted session - check "
                           "whether the change is half-applied before redoing it.")
            chunks.append(brief(carried, data_dir, CLI, header=header))

    if items:
        suffix, verb = plural(len(items))
        chunks.append(brief(
            items, data_dir, CLI,
            header=f"{len(items)} UI feedback item{suffix} {verb} sent from the review rail "
                   "and " + ("are" if suffix else "is") + " waiting to be implemented.",
        ))

    if not chunks:
        return 0

    json.dump({
        "hookSpecificOutput": {
            "hookEventName": event,
            "additionalContext": "\n\n".join(chunks),
        }
    }, sys.stdout)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # a broken hook must never block the session
        sys.stderr.write(f"uifb hook error (ignored): {exc}\n")
        sys.exit(0)

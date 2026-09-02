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

Which ledger gets read is its own problem. Walking up from the session's cwd
only finds the ledger when the session runs inside the reviewed project, and a
session started anywhere else exits silently while the reviewer waits - see
`store.live_servers`. So the cwd ledger is joined by the ledger of any review
server that is actually serving right now.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from render import brief, summarize  # noqa: E402
from store import DIR_NAME, FILE_NAME, Store, find_project_root, live_servers  # noqa: E402

CLI = Path(__file__).resolve().parent / "uifb.py"


def plural(n: int) -> tuple[str, str]:
    """(suffix, verb) so the briefing reads as English at any count."""
    return ("s", "were") if n != 1 else ("", "was")


def truthy(name: str, default: bool = True) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off")


def opted_in(root: Path) -> bool:
    """A project has opted in once its ledger file exists. Never speak in one
    that has not - a stray hook firing in unrelated repos is how people learn
    to delete hooks."""
    return (root / DIR_NAME / FILE_NAME).exists()


def candidates(payload: dict) -> list[tuple[Path, bool]]:
    """Every ledger this session should answer for, as (root, is_own).

    `is_own` marks the project the session is actually sitting in, so a
    briefing pulled from somewhere else can say where it came from instead of
    sending the agent editing the wrong checkout.
    """
    # An explicit pin wins outright: it is how a session is aimed at a project
    # it does not live in, and replaces hand-written wrapper scripts that did
    # the same thing by rewriting the payload's cwd.
    pinned = os.environ.get("UIFB_ROOT")
    if pinned:
        root = Path(pinned).expanduser().resolve()
        return [(root, True)] if opted_in(root) else []

    own = find_project_root(payload.get("cwd") or os.getcwd())
    out: list[tuple[Path, bool]] = []
    seen: set[Path] = set()
    if opted_in(own):
        out.append((own, True))
        seen.add(own)

    if truthy("UIFB_CROSS_PROJECT", default=True):
        for entry in live_servers():
            root = Path(entry.get("root", "")).resolve()
            if root in seen or not opted_in(root):
                continue
            out.append((root, False))
            seen.add(root)

    return out


def label(root: Path, is_own: bool) -> str:
    return "" if is_own else f" The review surface for this batch is {root}, "\
                             "so the change belongs in that checkout, not this one."


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}

    event = payload.get("hook_event_name") or ""
    if event not in ("Stop", "UserPromptSubmit", "SessionStart"):
        return 0

    roots = candidates(payload)
    if not roots:
        return 0

    if event == "Stop":
        return on_stop(roots)
    return emit_context(roots, event, include_summary=(event == "SessionStart"))


def on_stop(roots: list[tuple[Path, bool]]) -> int:
    chunks: list[str] = []
    for root, is_own in roots:
        data_dir = root / DIR_NAME
        items = Store(data_dir).take_undelivered()
        if not items:
            continue
        suffix, _ = plural(len(items))
        chunks.append(brief(
            items, data_dir, CLI,
            header=f"The reviewer just sent {len(items)} UI feedback item{suffix} from the "
                   "review rail. Work through them now, before ending the turn."
                   + label(root, is_own),
        ))

    if not chunks:
        return 0
    # Exit 2 is the documented way to keep a Stop from landing; stderr is what
    # gets handed back as the reason.
    sys.stderr.write("\n\n".join(chunks) + "\n")
    return 2


def emit_context(roots: list[tuple[Path, bool]], event: str, *, include_summary: bool) -> int:
    chunks: list[str] = []

    for root, is_own in roots:
        data_dir = root / DIR_NAME
        store = Store(data_dir)
        items = store.take_undelivered()

        if include_summary:
            counts = store.counts()
            if any(counts.get(k) for k in ("open", "sent", "in_progress")):
                chunks.append(f"UI feedback ledger ({data_dir}): {summarize(counts)}.")

            # A fresh session has no memory of what an earlier one was handed,
            # so re-brief anything still open in full. Carrying only a count
            # would leave the agent knowing work exists but not what it is -
            # which is how unfinished items quietly become abandoned ones.
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
                chunks.append(brief(carried, data_dir, CLI,
                                    header=header + label(root, is_own)))

        if items:
            suffix, verb = plural(len(items))
            chunks.append(brief(
                items, data_dir, CLI,
                header=f"{len(items)} UI feedback item{suffix} {verb} sent from the review rail "
                       "and " + ("are" if suffix else "is") + " waiting to be implemented."
                       + label(root, is_own),
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

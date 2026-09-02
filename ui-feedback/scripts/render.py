"""Turning stored items into the text the agent actually reads.

Kept apart from the CLI and the hook because both hand the agent the same
briefing, and a review item that reads differently depending on which door it
came through is a good way to get two different fixes for one complaint.
"""

from __future__ import annotations

from pathlib import Path

CLI_HINT = "python3 {cli}"


def brief(items: list[dict], data_dir: Path, cli: Path, *, header: str) -> str:
    """One implementable briefing per item: what to change, where it lives, and
    how to report back."""
    lines = [header, ""]
    lines.append(f"Ledger: {data_dir / 'feedback.json'}")
    lines.append("")

    for item in items:
        lines.extend(_one(item, data_dir))
        lines.append("")

    cmd = CLI_HINT.format(cli=cli)
    lines.append("How to work these:")
    lines.append(f"  1. Claim it     {cmd} status <id> in_progress")
    lines.append("  2. Make the change in the app's own source (never in .uifeedback/).")
    lines.append(f"  3. Close it     {cmd} status <id> done --note \"what you changed\"")
    lines.append("     or           {c} status <id> wont_fix --note \"why not\"".format(c=cmd))
    lines.append("")
    lines.append("The reviewer's rail updates live as you set each status, so claim an item "
                 "before you start rather than after you finish.")
    return "\n".join(lines)


def _one(item: dict, data_dir: Path) -> list[str]:
    t = item.get("target") or {}
    out = [f"### {item.get('id')} [{item.get('kind', 'change')}] {item.get('title', '')}".rstrip()]

    where = []
    if t.get("route"):
        where.append(f"route {t['route']}")
    vp = t.get("viewport") or {}
    if vp.get("w"):
        where.append(f"viewport {vp['w']}x{vp['h']}")
    if where:
        out.append("- " + "  ".join(where))

    region = t.get("mode") == "region"
    if region:
        rect = t.get("rect") or {}
        out.append(f"- marked area: {rect.get('w')}x{rect.get('h')} at "
                   f"({rect.get('x')},{rect.get('y')})")
    if t.get("selector"):
        # A region's selector is whatever sat under the centre of the box - a
        # starting point, not the subject. Saying so stops the agent from
        # "fixing" one element when the complaint was about a whole area.
        label = "element under the centre of the box" if region else "element"
        out.append(f"- {label}: `{t['selector']}`")
    if t.get("text"):
        out.append(f'- element text: "{t["text"]}"')
    if t.get("source_hint"):
        out.append(f"- source: {t['source_hint']}"
                   + (f" (component {t['component']})" if t.get("component") else ""))
    elif t.get("component"):
        out.append(f"- component: {t['component']}")
    if t.get("style_scope"):
        out.append(f"- scoped-style attribute: {t['style_scope']} "
                   "(grep this to find the file when no source path was captured)")
    if t.get("in_shadow_dom"):
        out.append("- note: the element lives inside a shadow root, so the selector is "
                   "relative to that root, not to `document`")
    if item.get("screenshot"):
        out.append(f"- screenshot: {data_dir / item['screenshot']} "
                   "(the violet outline is exactly what was marked)")

    body = (item.get("body") or "").strip()
    if body:
        out.append("")
        out.append("  " + body.replace("\n", "\n  "))

    thread = item.get("thread") or []
    if thread:
        out.append("")
        out.append("  Earlier on this item:")
        for note in thread[-4:]:
            who = "AI" if note.get("role") == "agent" else "reviewer"
            out.append(f"    - {who}: {note.get('text', '')}")

    return out


def summarize(counts: dict) -> str:
    parts = []
    for key, label in (("open", "draft"), ("sent", "waiting for you"),
                       ("in_progress", "in progress"), ("done", "done"),
                       ("wont_fix", "won't fix")):
        if counts.get(key):
            parts.append(f"{counts[key]} {label}")
    return ", ".join(parts) if parts else "nothing recorded yet"

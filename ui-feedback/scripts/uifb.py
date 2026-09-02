#!/usr/bin/env python3
"""uifb - the review loop's command line.

  uifb.py serve --target http://localhost:5173     start the review surface
  uifb.py list [--status active]                   what is on the ledger
  uifb.py show fb-0003                             one item, in full
  uifb.py status fb-0003 in_progress               claim it
  uifb.py status fb-0003 done --note "..."         close it
  uifb.py install-hooks                            automatic pickup by Claude
  uifb.py doctor                                   is anything misconfigured

Standard library only. Run it with any python3.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from render import brief, summarize  # noqa: E402
from store import DIR_NAME, STATUSES, Store, find_project_root  # noqa: E402

HERE = Path(__file__).resolve().parent
HOOK = HERE / "hook_uifb.py"
DEFAULT_PORT = 7788


# ------------------------------------------------------------------- helpers

def resolve_root(explicit: str | None) -> Path:
    return Path(explicit).resolve() if explicit else find_project_root()


def get_store(args) -> tuple[Store, Path]:
    root = resolve_root(getattr(args, "root", None))
    return Store(root / DIR_NAME), root


def port_busy(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", port)) == 0


def reachable(url: str) -> tuple[bool, str]:
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=4) as resp:
            return True, f"HTTP {resp.status}"
    except urllib.error.HTTPError as exc:
        return True, f"HTTP {exc.code}"  # answering at all is what matters
    except Exception as exc:
        return False, str(exc)


def load_config(root: Path) -> dict:
    path = root / DIR_NAME / "config.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def save_config(root: Path, data: dict) -> None:
    path = root / DIR_NAME / "config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


# -------------------------------------------------------------------- serve

def cmd_serve(args) -> int:
    # Line buffering matters here: `serve` is normally launched in the
    # background with its output redirected to a log, and a buffered banner
    # means whoever tails that log sees an empty file and assumes it crashed.
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    root = resolve_root(args.root)
    saved = load_config(root)
    target = args.target or saved.get("target")
    if not target:
        print("error: no target. Pass --target http://localhost:5173 the first time.",
              file=sys.stderr)
        return 2
    if "://" not in target:
        target = "http://" + target
    port = args.port or saved.get("port") or DEFAULT_PORT

    if port_busy(port):
        print(f"error: port {port} is already in use. Either a review server is already "
              f"running (open http://127.0.0.1:{port}/__uifb/review) or pass --port.",
              file=sys.stderr)
        return 2

    ok, detail = reachable(target)
    save_config(root, {"target": target, "port": port})

    import server  # imported late so `uifb.py list` never pays for it

    httpd = server.serve(target, port, root, verbose=args.verbose)
    review_url = f"http://127.0.0.1:{port}/__uifb/review"
    store = Store(root / DIR_NAME)

    print(f"review surface  {review_url}")
    print(f"app under review {target}" + ("" if ok else f"   [not answering: {detail}]"))
    print(f"ledger          {root / DIR_NAME / 'feedback.json'}  ({summarize(store.counts())})")
    if not server._hooks_installed(root):
        print("hooks           not installed - run `uifb.py install-hooks` so sent feedback "
              "reaches Claude on its own")
    print("Ctrl-C to stop.")

    if args.open:
        webbrowser.open(review_url)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
    finally:
        httpd.server_close()
    return 0


# --------------------------------------------------------------------- read

def cmd_list(args) -> int:
    store, _ = get_store(args)
    items = store.items(status=args.status)
    if args.json:
        print(json.dumps(items, indent=2, ensure_ascii=False))
        return 0
    if not items:
        print(f"no items with status '{args.status}'.")
        return 0
    for item in items:
        target = item.get("target") or {}
        flag = " *" if item.get("status") == "sent" and not item.get("delivered_at") else "  "
        print(f"{flag}{item['id']}  {item['status']:<12} {item.get('kind', ''):<8} "
              f"{(target.get('route') or '/')[:22]:<22} {item.get('title', '')[:52]}")
    print(f"\n{summarize(store.counts())}   (* = not yet handed to the agent)")
    return 0


def cmd_show(args) -> int:
    store, _ = get_store(args)
    item = store.get(args.id)
    if not item:
        print(f"no such item: {args.id}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(item, indent=2, ensure_ascii=False))
        return 0
    print(brief([item], store.dir, Path(__file__).resolve(), header=f"Item {item['id']}"))
    return 0


def cmd_pending(args) -> int:
    """Claim whatever is waiting. Same path the hook uses, for when hooks are
    not installed and the agent is asked to check by hand."""
    store, _ = get_store(args)
    items = store.take_undelivered() if not args.peek else [
        i for i in store.items("sent") if not i.get("delivered_at")
    ]
    if not items:
        print("nothing waiting.")
        return 0
    print(brief(items, store.dir, Path(__file__).resolve(),
                header=f"{len(items)} item(s) waiting to be implemented."))
    return 0


# -------------------------------------------------------------------- write

def cmd_status(args) -> int:
    store, root = get_store(args)
    if args.new_status not in STATUSES:
        print(f"status must be one of: {', '.join(STATUSES)}", file=sys.stderr)
        return 2
    item = store.get(args.id)
    if not item:
        print(f"no such item: {args.id}", file=sys.stderr)
        return 1
    changes = {"status": args.new_status}
    if args.new_status in ("done", "wont_fix"):
        changes["resolution"] = args.note or None
    store.update(args.id, changes)
    if args.note:
        store.append_note(args.id, "agent", args.note)
    _nudge(root)
    print(f"{args.id}: {item['status']} -> {args.new_status}")
    return 0


def cmd_note(args) -> int:
    store, root = get_store(args)
    if not store.get(args.id):
        print(f"no such item: {args.id}", file=sys.stderr)
        return 1
    store.append_note(args.id, args.role, args.text)
    _nudge(root)
    print(f"note added to {args.id}")
    return 0


def _nudge(root: Path) -> None:
    """Poke a running server so the reviewer's rail repaints immediately.

    The CLI writes the file directly rather than going through the API, so that
    status changes still work with no server running; this is the one thing the
    file write cannot do by itself.
    """
    cfg = load_config(root)
    port = cfg.get("port") or DEFAULT_PORT
    try:
        urllib.request.urlopen(
            urllib.request.Request(f"http://127.0.0.1:{port}/__uifb/api/refresh"), timeout=0.6
        ).read()
    except Exception:
        pass


# ------------------------------------------------------------------- wiring

HOOK_EVENTS = {
    "SessionStart": "startup|resume|clear",
    "UserPromptSubmit": None,
    "Stop": None,
}


def cmd_install_hooks(args) -> int:
    root = resolve_root(args.root)
    settings_path = root / ".claude" / ("settings.local.json" if args.local else "settings.json")
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    settings = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"error: {settings_path} is not valid JSON - fix it first so nothing is lost.",
                  file=sys.stderr)
            return 2

    command = f'python3 "{HOOK}"'
    hooks = settings.setdefault("hooks", {})
    added = []
    for event, matcher in HOOK_EVENTS.items():
        entries = hooks.setdefault(event, [])
        already = any(
            "hook_uifb" in json.dumps(entry) for entry in entries if isinstance(entry, dict)
        )
        if already:
            continue
        entry = {"hooks": [{"type": "command", "command": command}]}
        if matcher:
            entry["matcher"] = matcher
        entries.append(entry)
        added.append(event)

    settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    Store(root / DIR_NAME)  # make sure the ledger exists, or the hook stays silent

    if added:
        print(f"wired {', '.join(added)} in {settings_path}")
    else:
        print(f"already wired in {settings_path}")
    print("Restart Claude Code (or /hooks) so it reloads the settings file.")
    return 0


def cmd_doctor(args) -> int:
    root = resolve_root(args.root)
    cfg = load_config(root)
    store = Store(root / DIR_NAME)
    port = args.port or cfg.get("port") or DEFAULT_PORT
    target = args.target or cfg.get("target")

    def line(ok, label, detail=""):
        print(f"  [{'ok' if ok else '--'}] {label}{('  ' + detail) if detail else ''}")

    print(f"project root    {root}")
    print("checks")
    line(sys.version_info >= (3, 8), f"python {sys.version.split()[0]}")
    line(store.path.exists(), f"ledger {store.path}", summarize(store.counts()))

    import server
    line(server._hooks_installed(root), "hooks installed",
         "" if server._hooks_installed(root) else "run: uifb.py install-hooks")

    if target:
        ok, detail = reachable(target)
        line(ok, f"app at {target}", detail)
    else:
        line(False, "no target recorded", "pass --target on the first serve")

    running = port_busy(port)
    line(True, f"port {port}", "review server already running" if running else "free")
    if running:
        print(f"\n  review surface: http://127.0.0.1:{port}/__uifb/review")
    return 0


# --------------------------------------------------------------------- main

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="uifb", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", help="project root (default: nearest .uifeedback or .git)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("serve", help="run the review surface")
    s.add_argument("--target", help="the app's dev server, e.g. http://localhost:5173")
    s.add_argument("--port", type=int, help=f"review port (default {DEFAULT_PORT})")
    s.add_argument("--open", action="store_true", help="open the review surface in a browser")
    s.add_argument("--verbose", action="store_true", help="log every proxied request")
    s.set_defaults(func=cmd_serve)

    s = sub.add_parser("list", help="list feedback items")
    s.add_argument("--status", default="active",
                   help="open|sent|in_progress|done|wont_fix|active|closed|all")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_list)

    s = sub.add_parser("show", help="show one item in full")
    s.add_argument("id")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_show)

    s = sub.add_parser("pending", help="claim everything the reviewer has sent")
    s.add_argument("--peek", action="store_true", help="look without claiming")
    s.set_defaults(func=cmd_pending)

    s = sub.add_parser("status", help="move an item along the ladder")
    s.add_argument("id")
    s.add_argument("new_status", metavar="status", help="|".join(STATUSES))
    s.add_argument("--note", help="what you changed, or why not")
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("note", help="add a note to an item's thread")
    s.add_argument("id")
    s.add_argument("text")
    s.add_argument("--role", default="agent", choices=["agent", "user"])
    s.set_defaults(func=cmd_note)

    s = sub.add_parser("install-hooks", help="let sent feedback reach Claude automatically")
    s.add_argument("--local", action="store_true",
                   help="write .claude/settings.local.json instead of settings.json")
    s.set_defaults(func=cmd_install_hooks)

    s = sub.add_parser("doctor", help="check the setup")
    s.add_argument("--target")
    s.add_argument("--port", type=int)
    s.set_defaults(func=cmd_doctor)

    return p


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

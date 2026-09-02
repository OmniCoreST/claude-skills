#!/usr/bin/env python3
"""End-to-end check of the review loop, against a throwaway project.

Run this when the loop misbehaves in a real project, to find out whether the
fault is in this tooling or in how it was pointed at the app. It exercises the
paths that are easy to break and hard to notice: overlay injection, the ledger
lifecycle, hook idempotency (a Stop hook that re-serves the same batch traps a
session in a loop) and the websocket tunnel that HMR rides on.

    python3 selftest.py            # quiet unless something fails
    python3 selftest.py -v         # show each check
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLI = HERE / "uifb.py"
HOOK = HERE / "hook_uifb.py"

VERBOSE = "-v" in sys.argv or "--verbose" in sys.argv
failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        if VERBOSE:
            print(f"  ok   {label}")
    else:
        failures.append(f"{label}{('  -> ' + detail) if detail else ''}")
        print(f"  FAIL {label}" + (f"  -> {detail}" if detail else ""))


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def http(url: str, method: str = "GET", body: bytes | None = None,
         ctype: str = "application/json"):
    req = urllib.request.Request(url, method=method, data=body)
    if body:
        req.add_header("Content-Type", ctype)
    with urllib.request.urlopen(req, timeout=6) as resp:
        return resp.status, resp.read(), dict(resp.getheaders())


def run_hook(event: str, cwd: Path):
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({"hook_event_name": event, "cwd": str(cwd)}),
        capture_output=True, text=True, timeout=20,
    )
    return proc.returncode, proc.stdout, proc.stderr


# --------------------------------------------------------------- fake target

PAGE = (b"<!doctype html><html><head><title>t</title></head><body>"
        b"<div id='card' data-testid='card'>hello</div>"
        b"<script>console.log(1)</script></body></html>")


def fake_app(port: int, seen: dict) -> None:
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", port))
    srv.listen(8)
    seen["srv"] = srv
    while True:
        try:
            conn, _ = srv.accept()
        except OSError:
            return
        threading.Thread(target=_serve_one, args=(conn, seen), daemon=True).start()


def _serve_one(conn: socket.socket, seen: dict) -> None:
    try:
        req = conn.recv(65536).decode("latin-1")
        if "upgrade: websocket" in req.lower():
            seen["ws_request"] = req
            conn.sendall(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n\r\n")
            while True:
                data = conn.recv(4096)
                if not data:
                    break
                conn.sendall(b"echo:" + data)
            return
        if " /csp " in req or req.startswith("GET /csp"):
            # A target that forbids framing and inline script; the proxy has to
            # strip those or the review shell shows an empty box.
            conn.sendall(
                b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n"
                b"X-Frame-Options: DENY\r\n"
                b"Content-Security-Policy: default-src 'none'\r\n"
                b"Content-Length: " + str(len(PAGE)).encode() + b"\r\n\r\n" + PAGE)
            return
        conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: "
                     + str(len(PAGE)).encode() + b"\r\n\r\n" + PAGE)
    except OSError:
        pass
    finally:
        try:
            conn.close()
        except OSError:
            pass


# ------------------------------------------------------------------- the run

def main() -> int:
    app_port, review_port = free_port(), free_port()
    seen: dict = {}
    threading.Thread(target=fake_app, args=(app_port, seen), daemon=True).start()
    time.sleep(0.3)

    tmp = Path(tempfile.mkdtemp(prefix="uifb-selftest-"))
    (tmp / ".git").mkdir()  # makes it look like a project root
    base = f"http://127.0.0.1:{review_port}"

    proc = subprocess.Popen(
        [sys.executable, str(CLI), "--root", str(tmp), "serve",
         "--target", f"http://127.0.0.1:{app_port}", "--port", str(review_port)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(40):
            try:
                http(f"{base}/__uifb/api/config")
                break
            except Exception:
                time.sleep(0.15)
        else:
            print("FAIL review server never came up")
            return 1

        print("proxy")
        status, body, _ = http(f"{base}/")
        check("proxies the app", status == 200 and b"hello" in body)
        check("injects the overlay once", body.count(b'data-uifb="1"') == 1,
              f"found {body.count(b'data-uifb=')}")
        check("injects before </body>", body.index(b"data-uifb") < body.index(b"</body>"))

        _, _, headers = http(f"{base}/csp")
        lowered = {k.lower() for k in headers}
        check("strips X-Frame-Options", "x-frame-options" not in lowered)
        check("strips Content-Security-Policy", "content-security-policy" not in lowered)

        status, asset, _ = http(f"{base}/__uifb/static/overlay.js")
        check("serves the overlay asset", status == 200 and b"attachShadow" in asset)
        status, shell, _ = http(f"{base}/__uifb/review")
        check("serves the review shell", status == 200 and b"feedback" in shell.lower())

        print("ledger")
        payload = json.dumps({
            "body": "spacing is wrong", "kind": "bug",
            "target": {"mode": "element", "route": "/", "selector": "[data-testid=\"card\"]",
                       "viewport": {"w": 1280, "h": 800}},
        }).encode()
        status, created, _ = http(f"{base}/__uifb/api/items", "POST", payload)
        item = json.loads(created)
        check("creates an item", status == 201 and item["status"] == "open")
        check("derives a title", item["title"] == "spacing is wrong")

        status, _, _ = http(f"{base}/__uifb/api/items/{item['id']}", "DELETE")
        check("a draft can be deleted", status == 200)

        status, created, _ = http(f"{base}/__uifb/api/items", "POST", payload)
        item = json.loads(created)
        http(f"{base}/__uifb/api/send", "POST", b"{}")
        status, after, _ = http(f"{base}/__uifb/api/items/{item['id']}")
        check("send moves it to sent", json.loads(after)["status"] == "sent")

        status = 0
        try:
            status, _, _ = http(f"{base}/__uifb/api/items/{item['id']}", "DELETE")
        except urllib.error.HTTPError as exc:
            status = exc.code
        check("a sent item cannot be deleted", status == 409)

        print("hooks")
        code, out, err = run_hook("Stop", tmp)
        check("Stop blocks when feedback is waiting", code == 2, f"exit {code}")
        check("Stop briefing names the item", item["id"] in err)
        check("Stop briefing carries the selector", "data-testid" in err)

        code, out, err = run_hook("Stop", tmp)
        check("Stop is silent the second time (no loop)", code == 0 and not err.strip(),
              f"exit {code}, stderr {err[:80]!r}")

        code, out, _ = run_hook("SessionStart", tmp)
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"] if out.strip() else ""
        check("SessionStart re-briefs unfinished work", item["id"] in ctx)

        subprocess.run([sys.executable, str(CLI), "--root", str(tmp), "status",
                        item["id"], "done", "--note", "fixed it"],
                       capture_output=True, text=True, timeout=20)
        status, after, _ = http(f"{base}/__uifb/api/items/{item['id']}")
        done = json.loads(after)
        check("CLI closes the item", done["status"] == "done")
        check("the note lands on the thread",
              any(n.get("text") == "fixed it" for n in done.get("thread", [])))

        code, out, _ = run_hook("SessionStart", tmp)
        check("a closed item stops being re-briefed",
              not out.strip() or item["id"] not in out)

        print("websocket (hot reload)")
        c = socket.create_connection(("127.0.0.1", review_port), timeout=5)
        c.sendall(b"GET /hmr HTTP/1.1\r\nHost: x\r\nUpgrade: websocket\r\n"
                  b"Connection: Upgrade\r\nSec-WebSocket-Key: k1\r\n\r\n")
        handshake = c.recv(4096)
        check("upgrade passes through", b"101" in handshake)
        c.sendall(b"ping")
        check("frames relay both ways", c.recv(4096) == b"echo:ping")
        check("upstream sees the ws headers", "Sec-WebSocket-Key: k1" in seen.get("ws_request", ""))
        check("host rewritten for upstream",
              seen.get("ws_request", "").lower().count("host:") == 1)

        # An HMR socket is silent between edits, and the tunnel used to inherit
        # its ten-second connect timeout - so it hung up on every idle socket,
        # the dev server reported a lost connection, and the reviewed app
        # reloaded on a loop. Catching that means actually waiting it out.
        if VERBOSE:
            print("  (holding the tunnel idle past the old ten-second limit)")
        time.sleep(11.5)
        try:
            c.sendall(b"still here")
            late = c.recv(4096)
        except OSError:
            late = b""
        check("an idle tunnel survives past ten seconds", late == b"echo:still here")
        c.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        srv = seen.get("srv")
        if srv:
            srv.close()

    print()
    if failures:
        print(f"{len(failures)} check(s) failed:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())

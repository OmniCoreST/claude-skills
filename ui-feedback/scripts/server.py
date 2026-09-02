"""Review server: a transparent proxy in front of the app's dev server.

The whole point of proxying rather than asking the app to import something is
that the reviewed project keeps zero feedback code. Everything the reviewer
touches is served from this process:

    /__uifb/review     the review shell (live app + feedback rail)
    /__uifb/static/*   shell + overlay assets
    /__uifb/api/*      REST + SSE over the feedback store
    everything else    proxied to the target dev server, with the overlay
                       injected into HTML responses on the way back

Because both the shell and the app are served from this one origin, the shell
can talk to the app frame directly instead of fighting cross-origin rules, and
the overlay can POST to the API with a plain relative fetch.

Standard library only - no pip install, so it runs wherever python3 does.
"""

from __future__ import annotations

import http.client
import json
import mimetypes
import queue
import re
import socket
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from store import KINDS, STATUSES, Store

ASSETS = Path(__file__).resolve().parent.parent / "assets"
PREFIX = "/__uifb"

# Headers that describe a single hop and must not be relayed onward.
HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
}

# Headers that would stop the app rendering inside the review shell, or would
# stop the injected overlay from running. The app itself is untouched - we only
# drop them from the copy the reviewer's browser sees, on localhost, in dev.
FRAME_BLOCKERS = {
    "content-security-policy", "content-security-policy-report-only",
    "x-frame-options", "strict-transport-security", "cross-origin-opener-policy",
    "cross-origin-embedder-policy", "cross-origin-resource-policy",
}

# Caching is dropped for everything proxied. A review loop exists so the
# reviewer can see a fix land; a browser answering from cache - or the upstream
# answering 304 off an ETag - shows them the version they already complained
# about and makes the tool look like it did nothing. Bandwidth is free here:
# this is localhost, in development, for as long as the review lasts.
CACHE_HEADERS = {"cache-control", "etag", "last-modified", "expires", "age", "pragma"}

INJECT_TAG = b'<script src="/__uifb/static/overlay.js" data-uifb="1" defer></script>'

_subscribers: list[queue.Queue] = []
_subscribers_lock = threading.Lock()


def broadcast(event: dict) -> None:
    """Tell every open shell that the store changed.

    The agent changes statuses from the CLI while the user is looking at the
    rail; without this the rail would quietly go stale and the user would think
    nothing was happening.
    """
    payload = json.dumps(event)
    with _subscribers_lock:
        targets = list(_subscribers)
    for q in targets:
        try:
            q.put_nowait(payload)
        except queue.Full:
            pass


class ReviewServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, addr, handler, *, target: str, store: Store, verbose: bool):
        super().__init__(addr, handler)
        parsed = urllib.parse.urlsplit(target)
        self.target = target.rstrip("/")
        self.target_scheme = parsed.scheme or "http"
        self.target_host = parsed.hostname or "127.0.0.1"
        self.target_port = parsed.port or (443 if self.target_scheme == "https" else 80)
        self.target_netloc = parsed.netloc
        self.store = store
        self.verbose = verbose


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "uifb"
    sys_version = ""

    # ------------------------------------------------------------- plumbing

    def log_message(self, fmt, *args):
        if getattr(self.server, "verbose", False):
            super().log_message(fmt, *args)

    def _body(self) -> bytes:
        length = self.headers.get("Content-Length")
        if length:
            try:
                return self.rfile.read(int(length))
            except (ValueError, OSError):
                return b""
        return b""

    def _send(self, code: int, body: bytes = b"", ctype: str = "text/plain; charset=utf-8",
              extra: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD" and body:
            self.wfile.write(body)

    def _json(self, payload, code: int = 200) -> None:
        self._send(code, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    # --------------------------------------------------------------- routing

    def _route(self) -> None:
        try:
            if self.headers.get("Upgrade", "").lower() == "websocket":
                self._tunnel_websocket()
                return
            path = urllib.parse.urlsplit(self.path).path
            if path == PREFIX or path.startswith(PREFIX + "/"):
                self._internal(path)
            else:
                self._proxy()
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True
        except Exception as exc:  # keep one bad request from killing the server
            self.log_message("handler error: %r", exc)
            try:
                self._send(500, f"uifb internal error: {exc}".encode("utf-8"))
            except Exception:
                self.close_connection = True

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = _route

    # ------------------------------------------------------------- internal

    def _internal(self, path: str) -> None:
        store: Store = self.server.store
        rest = path[len(PREFIX):].strip("/")

        if rest in ("", "review", "review/"):
            self._serve_asset("shell.html", "text/html; charset=utf-8")
            return

        if rest.startswith("static/"):
            self._serve_asset(rest[len("static/"):])
            return

        if rest.startswith("shots/"):
            resolved = store.shot_path(f"shots/{Path(rest).name}")
            if not resolved:
                self._send(404, b"no such screenshot")
                return
            self._send(200, resolved.read_bytes(), "image/png")
            return

        if rest == "api/config":
            self._json({
                "target": self.server.target,
                "project": store.dir.parent.name,
                "dataDir": str(store.dir),
                "statuses": list(STATUSES),
                "kinds": list(KINDS),
                # The rail phrases the handoff differently depending on this:
                # with hooks the agent is interrupted, without them the user has
                # to say something first. Guessing wrong makes the button lie.
                "hooksInstalled": _hooks_installed(store.dir.parent),
            })
            return

        if rest == "api/events":
            self._sse()
            return

        if rest == "api/refresh":
            # The CLI writes the ledger file directly so it works with no
            # server running; this is how it tells a server that IS running
            # that the reviewer's rail is now out of date.
            broadcast({"type": "external"})
            self._json({"ok": True})
            return

        if rest == "api/items":
            if self.command == "GET":
                params = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                status = (params.get("status") or [None])[0]
                self._json({"items": store.items(status=status), "counts": store.counts()})
                return
            if self.command == "POST":
                payload = self._read_json()
                if payload is None:
                    return
                item = store.add(payload)
                broadcast({"type": "created", "id": item["id"]})
                self._json(item, 201)
                return

        if rest == "api/send" and self.command == "POST":
            payload = self._read_json() or {}
            moved = store.send(payload.get("ids"))
            broadcast({"type": "sent", "count": len(moved)})
            self._json({"sent": [i["id"] for i in moved], "count": len(moved)})
            return

        m = re.match(r"api/items/([A-Za-z0-9_-]+)(?:/(screenshot|note))?$", rest)
        if m:
            item_id, sub = m.group(1), m.group(2)
            if sub == "screenshot" and self.command == "POST":
                raw = self._body()
                if not raw:
                    self._json({"error": "empty screenshot"}, 400)
                    return
                rel = store.save_shot(item_id, raw)
                store.update(item_id, {"screenshot": rel})
                broadcast({"type": "updated", "id": item_id})
                self._json({"screenshot": rel})
                return
            if sub == "note" and self.command == "POST":
                payload = self._read_json() or {}
                item = store.append_note(item_id, payload.get("role", "user"),
                                         payload.get("text", ""))
                broadcast({"type": "updated", "id": item_id})
                self._json(item or {"error": "not found"}, 200 if item else 404)
                return
            if sub is None:
                if self.command == "GET":
                    item = store.get(item_id)
                    self._json(item or {"error": "not found"}, 200 if item else 404)
                    return
                if self.command in ("PATCH", "PUT"):
                    payload = self._read_json()
                    if payload is None:
                        return
                    item = store.update(item_id, payload)
                    broadcast({"type": "updated", "id": item_id})
                    self._json(item or {"error": "not found"}, 200 if item else 404)
                    return
                if self.command == "DELETE":
                    ok, why = store.delete(item_id)
                    broadcast({"type": "deleted", "id": item_id})
                    self._json({"deleted": ok, "error": why or None}, 200 if ok else 409)
                    return

        self._send(404, b"no such uifb endpoint")

    def _read_json(self):
        raw = self._body()
        try:
            return json.loads(raw.decode("utf-8")) if raw else {}
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            self._json({"error": f"bad json: {exc}"}, 400)
            return None

    def _serve_asset(self, name: str, ctype: str | None = None) -> None:
        target = (ASSETS / name).resolve()
        if not str(target).startswith(str(ASSETS.resolve())) or not target.is_file():
            self._send(404, b"no such asset")
            return
        guessed = ctype or mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if guessed.startswith("text/") or guessed in ("application/javascript", "application/json"):
            guessed += "; charset=utf-8" if "charset" not in guessed else ""
        self._send(200, target.read_bytes(), guessed)

    def _sse(self) -> None:
        q: queue.Queue = queue.Queue(maxsize=64)
        with _subscribers_lock:
            _subscribers.append(q)
        self.close_connection = True
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(b": connected\n\n")
            self.wfile.flush()
            while True:
                try:
                    payload = q.get(timeout=20)
                    self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")  # keeps proxies and tabs awake
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            with _subscribers_lock:
                if q in _subscribers:
                    _subscribers.remove(q)

    # ---------------------------------------------------------------- proxy

    def _upstream_headers(self) -> list[tuple[str, str]]:
        out = []
        for key, value in self.headers.items():
            low = key.lower()
            if low in HOP_BY_HOP or low == "host":
                continue
            # Strip conditional-request headers too, or the upstream answers
            # 304 Not Modified with an empty body and the overlay never gets
            # injected into it.
            if low in ("if-none-match", "if-modified-since", "if-match", "if-range"):
                continue
            if low == "accept-encoding":
                # Ask for plain bytes so HTML can be edited without inflating it.
                continue
            out.append((key, value))
        out.append(("Host", self.server.target_netloc))
        out.append(("Accept-Encoding", "identity"))
        return out

    def _proxy(self) -> None:
        body = self._body()
        conn_cls = (http.client.HTTPSConnection if self.server.target_scheme == "https"
                    else http.client.HTTPConnection)
        try:
            conn = conn_cls(self.server.target_host, self.server.target_port, timeout=60)
            conn.putrequest(self.command, self.path, skip_host=True, skip_accept_encoding=True)
            for key, value in self._upstream_headers():
                conn.putheader(key, value)
            conn.endheaders(body if body else None)
            resp = conn.getresponse()
        except (OSError, http.client.HTTPException) as exc:
            self._unreachable(exc)
            return

        ctype = resp.getheader("Content-Type", "") or ""
        is_html = "text/html" in ctype.lower()
        is_stream = "text/event-stream" in ctype.lower()
        length = resp.getheader("Content-Length")

        if is_html:
            self._proxy_html(resp, ctype)
        elif is_stream or length is None:
            self._proxy_stream(resp)
        else:
            self._proxy_buffered(resp, int(length))
        try:
            conn.close()
        except Exception:
            pass

    def _response_headers(self, resp, *, drop_length: bool) -> list[tuple[str, str]]:
        out = [("Cache-Control", "no-store")]
        for key, value in resp.getheaders():
            low = key.lower()
            if low in HOP_BY_HOP or low in FRAME_BLOCKERS or low in CACHE_HEADERS:
                continue
            if low in ("content-length", "content-encoding") and drop_length:
                continue
            if low == "location":
                value = self._rewrite_location(value)
            if low == "set-cookie":
                value = self._rewrite_cookie(value)
            out.append((key, value))
        return out

    def _rewrite_location(self, value: str) -> str:
        """Keep redirects on the review origin, otherwise the first login
        bounce would drop the reviewer out of the proxy and the overlay would
        vanish mid-session."""
        parsed = urllib.parse.urlsplit(value)
        if parsed.netloc and parsed.netloc == self.server.target_netloc:
            return urllib.parse.urlunsplit(("", "", parsed.path or "/", parsed.query,
                                            parsed.fragment))
        return value

    def _rewrite_cookie(self, value: str) -> str:
        parts = [p for p in value.split(";")
                 if p.strip().lower() != "secure"
                 and not p.strip().lower().startswith("domain=")]
        return ";".join(parts)

    def _proxy_html(self, resp, ctype: str) -> None:
        raw = resp.read()
        injected = _inject(raw, (self.headers.get("Sec-Fetch-Dest") or "").lower())
        headers = self._response_headers(resp, drop_length=True)
        self.send_response(resp.status)
        for key, value in headers:
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(injected)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(injected)

    def _proxy_buffered(self, resp, length: int) -> None:
        raw = resp.read(length) if length else b""
        headers = self._response_headers(resp, drop_length=True)
        self.send_response(resp.status)
        for key, value in headers:
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(raw)

    def _proxy_stream(self, resp) -> None:
        """Relay an open-ended body (the app's own SSE, chunked responses).

        Buffering these would hang the app's live features behind the proxy,
        which would make the review surface lie about how the app behaves.
        """
        self.close_connection = True
        headers = self._response_headers(resp, drop_length=True)
        self.send_response(resp.status)
        for key, value in headers:
            self.send_header(key, value)
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            while True:
                chunk = resp.read(8192)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def _unreachable(self, exc: Exception) -> None:
        page = _UNREACHABLE_HTML.replace("{{target}}", _escape(self.server.target)) \
                               .replace("{{error}}", _escape(str(exc)))
        self._send(502, page.encode("utf-8"), "text/html; charset=utf-8")

    # ------------------------------------------------------------ websocket

    def _tunnel_websocket(self) -> None:
        """Raw byte tunnel for the dev server's HMR socket.

        Without this the app still renders, but every save would need a manual
        reload - and a review loop where the fix does not appear by itself is a
        much worse loop.
        """
        self.close_connection = True
        try:
            upstream = socket.create_connection(
                (self.server.target_host, self.server.target_port), timeout=10)
        except OSError as exc:
            self.log_message("ws upstream failed: %r", exc)
            return

        # The connect timeout must not survive into the stream. create_connection
        # leaves it on the socket, and an HMR socket is silent by definition
        # between edits - so recv() below would raise after ten idle seconds and
        # tear the tunnel down. The dev server reads that as a lost connection;
        # Vite's client then polls, gets an answer, and reloads the page. To the
        # reviewer the app appears to reload every ten seconds, forever, which
        # reads like a bug in their app rather than in this proxy.
        upstream.settimeout(None)

        lines = [f"{self.command} {self.path} HTTP/1.1"]
        for key, value in self.headers.items():
            if key.lower() == "host":
                continue
            lines.append(f"{key}: {value}")
        lines.append(f"Host: {self.server.target_netloc}")
        handshake = ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1")

        try:
            upstream.sendall(handshake)
        except OSError:
            upstream.close()
            return

        def pump_up():
            try:
                while True:
                    # read1 drains whatever the header parser already buffered
                    # before falling through to a real socket read.
                    data = self.rfile.read1(65536)
                    if not data:
                        break
                    upstream.sendall(data)
            except (OSError, ValueError):
                pass
            finally:
                _quiet_shutdown(upstream)

        def pump_down():
            try:
                while True:
                    data = upstream.recv(65536)
                    if not data:
                        break
                    self.connection.sendall(data)
            except (OSError, ValueError):
                pass
            finally:
                _quiet_shutdown(self.connection)

        up = threading.Thread(target=pump_up, daemon=True)
        up.start()
        pump_down()
        up.join(timeout=1)
        try:
            upstream.close()
        except OSError:
            pass


def _quiet_shutdown(sock) -> None:
    try:
        sock.shutdown(socket.SHUT_WR)
    except OSError:
        pass


_BODY_RE = re.compile(rb"</body\s*>", re.IGNORECASE)
_HTML_RE = re.compile(rb"</html\s*>", re.IGNORECASE)


HTML_HINTS = (b"<!doctype html", b"<html", b"<head", b"<body", b"<title", b"<meta charset")


def _inject(raw: bytes, fetch_dest: str = "") -> bytes:
    """Put the overlay tag into a page, once.

    Some guard is needed because dev servers also return `text/html` for
    fragments fetched by XHR, and injecting into one of those would run a
    second overlay inside the page that requested it.

    The browser states the answer outright: `Sec-Fetch-Dest` is
    `document`/`iframe` for a navigation and `empty` for a fetch. That beats
    sniffing the markup, which got this wrong on a real file - a hand-written
    page starting straight at `<meta charset>`, with no doctype, html or body
    tag, renders perfectly in a browser but failed a tag-presence test and so
    silently never got the panel. Sniffing stays as the fallback for clients
    that send no such header (curl, older browsers), and is now generous about
    which tag proves it is a page.
    """
    if b'data-uifb="1"' in raw:
        return raw
    if fetch_dest:
        if fetch_dest not in ("document", "iframe", "frame"):
            return raw
    elif not any(hint in raw[:4096].lower() for hint in HTML_HINTS):
        return raw
    m = _BODY_RE.search(raw) or _HTML_RE.search(raw)
    if m:
        return raw[:m.start()] + INJECT_TAG + raw[m.start():]
    return raw + INJECT_TAG


def _hooks_installed(project_root: Path) -> bool:
    for name in ("settings.json", "settings.local.json"):
        path = project_root / ".claude" / name
        if path.exists() and "hook_uifb" in path.read_text(encoding="utf-8", errors="ignore"):
            return True
    return False


def _escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


_UNREACHABLE_HTML = """<!doctype html><html><head><meta charset="utf-8">
<title>dev server unreachable</title></head>
<body style="margin:0;font:14px/1.6 ui-sans-serif,system-ui,sans-serif;background:#0f1720;color:#e6edf3">
<div style="max-width:38rem;margin:12vh auto;padding:2rem">
<h1 style="font-size:1.1rem;margin:0 0 .75rem">The app is not answering</h1>
<p style="margin:0 0 .75rem;color:#9fb0c0">The review proxy could not reach
<code style="background:#1b2733;padding:.1rem .35rem;border-radius:4px">{{target}}</code>.</p>
<p style="margin:0 0 1.25rem;color:#9fb0c0">Start the dev server, then reload. The feedback
rail and everything already recorded are unaffected.</p>
<pre style="background:#1b2733;padding:.75rem;border-radius:6px;overflow:auto;color:#c2d0de">{{error}}</pre>
<button onclick="location.reload()" style="margin-top:1rem;background:#2f81f7;border:0;color:#fff;
padding:.5rem .9rem;border-radius:6px;font:inherit;cursor:pointer">Retry</button>
</div></body></html>"""


def serve(target: str, port: int, root: Path, *, verbose: bool = False) -> ReviewServer:
    store = Store(Path(root) / ".uifeedback")
    httpd = ReviewServer(("127.0.0.1", port), Handler, target=target, store=store,
                         verbose=verbose)
    return httpd

# Troubleshooting

Work down from the symptom. Run `uifb.py doctor` first - it answers most of the
setup questions in one shot - and `selftest.py -v` when you suspect the tooling
itself rather than this particular project.

## Contents

- [The panel does not appear](#the-panel-does-not-appear)
- [The app frame is blank](#the-app-frame-is-blank)
- [The app reloads over and over](#the-app-reloads-over-and-over)
- [Hot reload stopped working](#hot-reload-stopped-working)
- [HTTPS targets](#https-targets)
- [Login and external auth](#login-and-external-auth)
- [Service workers](#service-workers)
- [Selectors that do not survive](#selectors-that-do-not-survive)
- [No source hint](#no-source-hint)
- [Screenshots](#screenshots)
- [Feedback never reaches Claude](#feedback-never-reaches-claude)
- [Framework notes](#framework-notes)
- [Docker and remote dev servers](#docker-and-remote-dev-servers)

## The panel does not appear

Check in this order:

1. **Is the page HTML?** The overlay is injected only into responses whose
   content type is `text/html` and whose first 4 KB contain `<html`, `<body` or
   a doctype. A pure client-rendered app still qualifies - its shell document is
   HTML - but an app whose entry point is served with the wrong content type
   does not. `curl -sI http://127.0.0.1:7788/ | grep -i content-type`.
2. **Is it a nested frame?** The overlay deliberately mounts only in the
   outermost app frame. If the real UI lives in an iframe inside the app, the
   panel appears on the outer document, not the inner one.
3. **Already injected?** `curl -s http://127.0.0.1:7788/ | grep -c data-uifb`
   should print `1`.
4. **Console errors?** An exception thrown by the app before the deferred
   script runs will not stop the overlay, but one thrown *by* the overlay will.
   Report it - that is a bug in this skill, not in their app.

## The app frame is blank

Usually the app refuses to be framed, or refuses to run. The proxy strips
`X-Frame-Options`, CSP, HSTS and the `Cross-Origin-*` headers, so the common
causes are already handled. What is left:

- **A meta-tag CSP inside the HTML.** Header stripping cannot reach it. Ask
  before touching their source; the honest workaround is to review the app
  directly at `http://127.0.0.1:<port>/` instead of through the shell - the
  overlay still works there, only the rail is missing.
- **Frame-busting script** (`if (top !== self) top.location = self.location`).
  Rare outside legacy apps. Same workaround.
- **The dev server is down.** The frame shows a "The app is not answering"
  page naming the target. Start it and reload.

## The app reloads over and over

The frame reloads on a metronome - every ten seconds or so - and the browser
console repeats one line:

    [vite] server connection lost. Polling for restart...

Nothing is wrong with the app, and nothing restarted. The HMR websocket was
dropped; the dev server's client reacts to a dropped socket by polling until
the server answers and then reloading the page. The server never went away, so
it answers at once, and the loop never ends. Vite says it out loud, but any
dev server with reconnect-and-reload logic produces the same shape.

The reviewer sees this as a bug in their app, and it makes the review surface
unusable - a marked element is gone before they finish typing.

This was a bug in this skill, found the first time the loop was pointed at a
Vite 6 dev server and fixed in `_tunnel_websocket` (`scripts/server.py`):
`socket.create_connection(..., timeout=10)` leaves the connect timeout on the
socket, so `recv()` raised after ten idle seconds and tore the tunnel down. An
HMR socket is silent between edits, so it was always idle. The fix is one line -
`upstream.settimeout(None)` after connecting - and `selftest.py` now holds a
tunnel idle past that limit to keep it fixed.

So if you meet this symptom:

1. Run `selftest.py -v`. If **an idle tunnel survives past ten seconds** fails,
   the timeout line is missing again - restore it.
2. If that check passes, the dev server is hanging up on its own idle sockets.
   That is a per-project setting, not something to fix from here.

Do not reach for the dev server's config first. Pointing the HMR client
straight at the dev server (Vite's `server.hmr.clientPort`) also makes the
symptom disappear, which makes it a convincing wrong answer: it bypasses the
tunnel instead of repairing it, and it needs a change in a repo that is
supposed to stay clean.

## Hot reload stopped working

If the app is *reloading* rather than sitting still, read
[the section above](#the-app-reloads-over-and-over) instead - that is a
different fault with a different fix.

The proxy tunnels `Upgrade: websocket` verbatim, so HMR normally survives. When
it does not, the usual cause is a dev server configured to advertise an
absolute HMR URL pointing at its own port, which the browser then dials
directly, outside the proxy. Vite's `server.hmr.clientPort` is the setting
involved. Confirm by watching the browser's network panel for a websocket to
the *app's* port rather than the review port.

This is a per-project dev-server setting, so raise it with the user rather than
editing their config unasked. Reviewing still works throughout - only automatic
refresh is lost, and the reload button in the top bar covers it.

## HTTPS targets

`--target https://localhost:5173` works, but a dev server's self-signed
certificate will make the proxy's upstream connection fail. Prefer pointing at
the plain-HTTP port when one exists. If HTTPS is the only option and the
certificate is not trusted by the system store, say so plainly rather than
disabling verification - silently accepting any certificate is not a change to
make on someone's behalf.

## Login and external auth

Same-host redirects are rewritten to stay on the review origin, and cookies are
de-scoped so they stick to localhost. That covers ordinary session login.

An OAuth bounce to an external provider leaves the proxy by design - the
reviewer lands on the provider's real domain, signs in, and comes back. If the
provider's redirect URI points at the app's own port, they will return to the
unproxied app. Either add the review port as an allowed redirect URI in that
provider's config (their call, not yours), or log in first on the app's own
port and then open the review surface, since the cookie is shared by host.

## Service workers

A previously installed service worker on `127.0.0.1` may serve cached responses
that predate the proxy, so the overlay never gets injected. Unregister it from
the browser's Application panel, or use a different review port - the worker's
scope is per origin, and the port is part of the origin.

## Selectors that do not survive

Selectors skip class names that look build-generated, and prefer test ids and
unique element ids, precisely so they survive the rebuild the fix causes. They
still cannot survive a rewrite of the markup.

When the rail's **Reveal** cannot match an item, it falls back to the recorded
coordinates and says so. That is not a failure to act on - the comment, the
screenshot and the route are still exact. Read the item, not the selector.

## No source hint

Expected in these cases: production or minified builds (the debug fields are
stripped), frameworks other than Vue/React/Svelte, and plain server-rendered
HTML. Fall back to the scoped-style attribute, then to grepping the selector's
test id or class names, then to the route.

React 19 removed `_debugSource` from fibers; the component name is still
recovered from the owner chain, so `component:` may appear without `source:`.

## Screenshots

- **Nothing attaches.** The capture is granted per shell session and the top-bar
  button must read `Screenshots: on`. Grant it once and it covers every later
  item.
- **The crop is offset.** Zooming the browser after granting the capture
  invalidates the scale factor between CSS pixels and video pixels. Re-grant.
- **Nothing to grant.** `getDisplayMedia` needs a secure context;
  `http://127.0.0.1` counts as one, but `http://<lan-ip>` does not. Use the
  loopback address.

Items without screenshots keep their exact rect, route and viewport, so they
remain implementable - a missing picture is a downgrade, not a blocker.

## Feedback never reaches Claude

1. `uifb.py doctor` - is `hooks installed` ok?
2. Was Claude Code restarted after `install-hooks`? Settings are read at start.
3. `uifb.py list --status sent` - is anything actually sent? Items sitting at
   `open` are still drafts; the reviewer has not pressed Send.
4. Fire the hook by hand (see `hooks.md`). `exit=2` with text means the store
   and hook are fine and the problem is in the settings wiring.

## Framework notes

- **Vite / Vue / React dev servers** - nothing to configure; see the HMR note
  above.
- **Next.js dev** - works through the proxy. The dev overlay is a nested
  element in the same document, so the panel and it can overlap visually;
  neither breaks the other.
- **Django / Rails / Laravel / Go templates** - ideal case. Server-rendered
  HTML gets the overlay, no source hint is available, and the selector plus
  route point at the template.
- **Storybook** - point the target at the Storybook port. Stories render in an
  inner iframe, so the panel mounts on the outer document; review a story with
  its own URL open directly if you need to mark inside it.
- **Static sites** - `python3 -m http.server` as the target works fine, which
  is also how `selftest.py` exercises the proxy.

## Docker and remote dev servers

The review server binds `127.0.0.1` only, deliberately - it exposes a write API
over the project's ledger and should not be reachable from the network.

To review a dev server inside a container, publish that container's port to the
host and point `--target` at the published host port. To review something on
another machine, forward its port to localhost over SSH first
(`ssh -L 5173:localhost:5173 host`) and target the forwarded port. In both
cases the reviewer's browser and the review server stay on the same machine,
which is what the one-origin design assumes.

# Architecture

Read this before changing the tooling, or when behaviour is confusing enough
that guessing would be slower than understanding.

## Contents

- [The shape of it](#the-shape-of-it)
- [Why a proxy](#why-a-proxy)
- [What the proxy rewrites](#what-the-proxy-rewrites)
- [The injected overlay](#the-injected-overlay)
- [The review shell](#the-review-shell)
- [The store](#the-store)
- [Item schema](#item-schema)
- [HTTP API](#http-api)
- [Files](#files)

## The shape of it

```
                    browser
   ┌──────────────────────────────────────────────┐
   │  /__uifb/review          the review shell     │
   │  ┌────────────────────────┬────────────────┐  │
   │  │ <iframe src="/">       │ feedback rail  │  │
   │  │   the app, proxied     │  open / sent   │  │
   │  │   + overlay injected   │  in progress   │  │
   │  └────────────────────────┴────────────────┘  │
   └───────────────┬──────────────────────────────┘
                   │ one origin: 127.0.0.1:7788
        ┌──────────┴───────────┐
        │  uifb.py serve       │
        │  proxy + API + SSE   │
        └────┬────────────┬────┘
             │            │
   app dev server    .uifeedback/feedback.json
   (untouched)        │
                      │  read + claimed by
                      └──► hook_uifb.py ──► Claude's context
```

## Why a proxy

Three problems solve themselves at once:

**No code in their repo.** The overlay is injected into HTML responses in
flight. Nothing to import, nothing to remember to remove, nothing to ship by
accident, and it works the same for Vue, React, Django templates or a static
folder because it operates on HTTP, not on a build system.

**One origin.** The shell and the app share `127.0.0.1:<port>`, so the shell can
reach into the app frame and the overlay can call the API with a relative
`fetch`. Serving the shell from a second port would make every one of those
interactions a cross-origin negotiation.

**Framing works.** Dev servers commonly send `X-Frame-Options` or a CSP that
would leave the shell showing an empty box. The proxy drops those headers from
the copy the reviewer's browser gets; the app itself is not modified.

## What the proxy rewrites

Request direction:

- `Host` is set to the upstream's netloc.
- `Accept-Encoding` is forced to `identity`, so HTML can be edited as bytes
  without inflating and re-deflating it.
- Hop-by-hop headers are dropped.

Response direction:

- `X-Frame-Options`, `Content-Security-Policy`, `Strict-Transport-Security` and
  the `Cross-Origin-*` family are stripped - see above.
- `Location` on a same-host redirect is made relative, so a login bounce keeps
  the reviewer inside the proxy instead of dumping them on the raw dev server
  with no overlay.
- `Set-Cookie` loses `Domain=` and `Secure`, so cookies stick on plain-HTTP
  localhost.
- HTML gets `<script src="/__uifb/static/overlay.js">` inserted before
  `</body>`, once, and only when the body actually looks like a document -
  dev servers return `text/html` for partials and error frames too, and
  injecting into those would run the overlay twice in one page.

Body handling differs by kind, deliberately:

| Response | Handling | Why |
|---|---|---|
| `text/html` | buffered, injected, re-lengthed | injection needs the whole document |
| `text/event-stream` | streamed, connection closed at the end | buffering would hang the app's own live features |
| no `Content-Length` | streamed | chunked bodies have no known length |
| everything else | read to length, forwarded | keeps keep-alive working |

`Upgrade: websocket` bypasses all of it and becomes a raw byte tunnel in both
directions. That is what hot reload rides on, and a review loop where the fix
does not appear by itself is a much worse loop. The client side is pumped with
`rfile.read1()` rather than `recv()`, because the header parser has usually
already buffered bytes past the request line and a raw socket read would skip
them.

## The injected overlay

`assets/overlay.js`, mounted into a shadow root on a host with `all: initial`.
No imports, no fonts, no globals except one guard flag. It only mounts in the
outermost app frame - a nested iframe inside the app is proxied too, and would
otherwise stack a second panel.

Modes are `idle`, `pick`, `region` and `composing`. `composing` exists because
while the comment box is open the page must stop being selectable: without it,
a click on the panel's own kind chips reads as picking a new element and throws
away the half-written comment. For the same reason every document-level
listener ignores events whose `composedPath()` contains our host - the shadow
boundary is transparent to those listeners.

**Selector strategy**, most to least preferred: a `data-testid`-family
attribute; a unique non-numeric `id`; otherwise a path built upwards, taking
tag plus up to two non-volatile class names, adding `:nth-of-type` only to
break ties, stopping as soon as the accumulated selector is unique. Class names
matching build-tool patterns (`css-xxxx`, `sc-xxxx`, `jsx-123`, `svelte-xxxxx`,
CSS-module hashes) are skipped: a selector built from them would not survive
the rebuild that the fix itself causes.

**Source hints** are read from framework dev-build internals - Vue 3
(`__vueParentComponent.type.__file`), Vue 2 (`__vue__.$options.__file`), Svelte
(`__svelte_meta.loc.file`), React (`_debugSource` on the fiber, walking up
owners). Every probe is wrapped in try/catch: these are private fields that
change between versions, and a missing hint is fine while an exception thrown
inside the reviewer's app is not. Vue's `data-v-xxxxxxx` scope attribute is
captured too - not a path, but a token that greps straight to the file.

**Pins** re-resolve each active item's selector on the current route and drop a
numbered marker, colour-coded by status, so past feedback is visible in place
rather than only in a list.

**The overlay shows no chrome inside the shell.** Its button dock and its pins
are for the standalone case - the app opened directly on its own port, where
this overlay is the whole interface. Framed by the shell, the top bar already
carries Mark element and Draw region and the rail already lists the feedback,
so a dock and markers over the app would duplicate both and put our furniture
in the middle of the design under review. `IN_SHELL` (`window.self !==
window.top`) decides; the dock's buttons are still constructed either way,
detached, so mode changes arriving over `postMessage` toggle their state
through one code path. What remains in the frame is only what the reviewer's
own action summons: the hover highlight while marking, the composer, and
transient toasts - including the one that reports a failed save.

## The review shell

`assets/shell.html/css/js`. Main pane is an iframe of the proxied app; the rail
is the ledger. It talks to the overlay over `postMessage` and to the store over
the API - it never touches app code, which is why the same rail works for any
stack.

Screenshots use one `getDisplayMedia({preferCurrentTab: true})` grant per
session, kept open and cropped per item, rather than a permission prompt each
time. The crop maths goes: item rect (iframe viewport coords) + iframe offset
in the shell → tab coords → scaled by `videoWidth / window.innerWidth`. The
marked area is stroked back onto the crop, because padding alone loses the
point - the reader has to know which part of the picture is being discussed.

Live updates come over SSE, with a 12-second poll as a fallback so a dropped
stream cannot leave the rail frozen. The CLI writes the ledger file directly
(so it works with no server running) and then pings `/__uifb/api/refresh` to
tell a running shell it is stale.

## The store

One JSON file plus PNG sidecars. A file, not process memory, because three
separate processes - server, CLI, hook - must agree on state, and because the
reviewer wants to see unfinished items days later.

Writes are atomic (`tmp` + `os.replace`) and serialised with an advisory
`flock`, so a hook firing mid-request cannot read a half-written file. Reads
are lock-free: a display path tolerates a stale read far better than it
tolerates blocking on a busy lock.

`take_undelivered()` claims and stamps in a single locked write. This is the
loop-safety guarantee for the `Stop` hook - see `hooks.md`.

## Item schema

```jsonc
{
  "id": "fb-0003",
  "created_at": "2026-08-14T09:41:00Z",
  "updated_at": "...",
  "sent_at": "...",
  "status": "open | sent | in_progress | done | wont_fix",
  "kind":   "bug | change | idea | question",
  "title":  "derived from the first line of body",
  "body":   "what the reviewer typed",
  "target": {
    "mode": "element | region",
    "route": "/dashboard",
    "url": "http://127.0.0.1:7788/dashboard",
    "viewport": { "w": 1440, "h": 900, "dpr": 2 },
    "rect": { "x": 12, "y": 340, "w": 360, "h": 120 },
    "scroll": { "x": 0, "y": 820 },
    "selector": "[data-testid=\"meter-card\"] > div.v",
    "alternatives": ["[aria-label=\"...\"]"],
    "tag": "div",
    "text": "94 kWh",
    "source_hint": "src/views/DashboardView.vue",
    "component": "MeterCard",
    "style_scope": "data-v-1a2b3c4d",
    "in_shadow_dom": false
  },
  "screenshot": "shots/fb-0003.png",
  "thread": [{ "role": "agent", "at": "...", "text": "..." }],
  "delivered_at": null,
  "resolution": null
}
```

Unknown keys on create are preserved. The overlay may capture context this
version of the store has no name for, and dropping it would silently lose
evidence the reviewer gathered.

## HTTP API

Everything under `/__uifb/`; every other path is proxied.

| Method | Path | Notes |
|---|---|---|
| GET | `/__uifb/review` | the shell |
| GET | `/__uifb/static/<file>` | shell + overlay assets |
| GET | `/__uifb/shots/<file>` | screenshots, path-traversal guarded |
| GET | `/__uifb/api/config` | target, project, statuses, `hooksInstalled` |
| GET | `/__uifb/api/items?status=` | `status` also accepts `active`, `closed`, `all` |
| POST | `/__uifb/api/items` | create; returns 201 + the item |
| GET/PATCH/DELETE | `/__uifb/api/items/<id>` | DELETE is 409 unless still `open` |
| POST | `/__uifb/api/items/<id>/screenshot` | raw PNG body |
| POST | `/__uifb/api/items/<id>/note` | `{role, text}` |
| POST | `/__uifb/api/send` | `{}` for all drafts, or `{ids: [...]}` |
| POST/GET | `/__uifb/api/refresh` | broadcast-only; how the CLI nudges the rail |
| GET | `/__uifb/api/events` | SSE; one message per mutation |

## Files

```
scripts/
  uifb.py        CLI: serve, list, show, pending, status, note, install-hooks, doctor
  server.py      proxy + injection + API + SSE + websocket tunnel
  store.py       the ledger: atomic writes, locking, status ladder
  render.py      items -> the briefing text the agent reads
  hook_uifb.py   Claude Code hook for SessionStart / UserPromptSubmit / Stop
  selftest.py    24 end-to-end checks; run when the loop misbehaves
assets/
  overlay.js     injected panel (shadow DOM, zero dependencies)
  shell.html/css/js   the review surface
```

Written against the Python standard library only, so it runs wherever `python3`
does with no install step - which matters because the projects it reviews often
have no Python in them at all.

---
name: ui-feedback
description: >
  Visual feedback loop for a web UI under development: the running app is shown
  in a local review surface where the reviewer marks an element or drags a box
  over an area, writes a comment, and sends it over for implementation - with a
  persistent list of open, in-progress and finished items that survives across
  sessions. Use when someone wants to review, annotate, mark up or leave
  comments on a running web interface; when they ask for a feedback, review or
  annotation setup for a site; or when they ask what UI feedback from earlier is
  still outstanding. It proxies their dev server and adds no code to their
  project, so prefer it over hand-building a comment widget into their app. Not
  for annotating a generated document, report or plan (that is a different
  tool), and not for building an end-user feedback form as a product feature.
---

# UI feedback loop

A reviewer looking at a screen can point at the problem in a second and spend
five minutes failing to describe it in words. This skill removes the
description step: the app runs inside a review surface, the reviewer marks the
thing itself, types a sentence, and the marked element - with its selector,
source file, route, viewport and a cropped screenshot - arrives in your context
as an implementable item.

Three properties are the whole point. Protect them.

**The reviewed project stays clean.** Nothing is imported into their app. A
local proxy sits in front of their dev server and injects the panel into HTML
on the way to the browser. Never "just add a script tag to index.html" - the
moment feedback code lives in their repo, someone ships it.

**The panel owes nothing to the site.** It renders in a shadow root with its
own reset, its own `uifb-` class names and no libraries, fonts or globals. That
isolation is what makes it trustworthy: a panel that inherited the app's CSS
would change shape per project, and a visual bug would become ambiguous - the
app's fault or ours?

**Nothing is lost between sessions.** Every item lives in
`.uifeedback/feedback.json` in the project, with a status ladder
(`open → sent → in_progress → done | wont_fix`). Unfinished work is re-briefed
to you at the start of the next session.

## Starting a session

```bash
SK=~/.claude/skills/ui-feedback/scripts

# 1. their dev server must already be running (vite, next, django, whatever)
# 2. point the review surface at it
python3 $SK/uifb.py serve --target http://localhost:5173 --open
```

Run it in the background so the session stays usable, then tell the user the
review URL it prints (`http://127.0.0.1:7788/__uifb/review`). `--open` launches
the browser; drop it when you cannot see their display.

The first time in a project, wire the hooks so their feedback reaches you
without them having to ask:

```bash
python3 $SK/uifb.py install-hooks           # this project only
python3 $SK/uifb.py install-hooks --user    # once, for every project
```

Say plainly that this edits `.claude/settings.json` (`--user` edits
`~/.claude/settings.json`) and needs a restart of Claude Code to take effect. If
they would rather not have hooks, everything still works - you just pick items
up with `uifb.py pending` when they mention they have sent some.

Feedback reaches a session two ways: the session sits inside the reviewed
project, or a review server for that project is running while the session works
elsewhere. `UIFB_ROOT=/path/to/project` pins a session to one ledger outright.
See `references/hooks.md`.

If the app is not up yet, start it the way that project starts it, or ask. Do
not guess a port: `uifb.py doctor` reports whether the target answers.

## What the reviewer does

They will not read a manual, so tell them the three things that matter:

- **Mark element** (or `Alt+M`), then click anything - the panel records a
  stable selector, the visible text, and the component/source file when the
  framework's dev build exposes it.
- **Draw region** (or `Alt+R`), then drag a box - for spacing, alignment,
  rhythm and "this whole area", which no single element describes.
- **Send to AI** hands the drafts over. Before that they are drafts and can be
  edited or deleted; after it they are on the record.

Also worth mentioning once: **Screenshots: off** in the top bar asks for one
tab-capture permission and then attaches a cropped picture, marked with a
violet outline, to every item from then on. Without it items still carry exact
coordinates - just no picture.

## When feedback arrives

With hooks installed it arrives on its own: mid-turn as a `Stop` that keeps the
turn alive, or with their next message. Each item comes as a briefing with the
route, selector, source hint and screenshot path.

Work them like this, and keep the status current as you go - the reviewer is
watching the rail move in real time, and a silent rail reads as a stalled agent:

```bash
python3 $SK/uifb.py status fb-0003 in_progress          # claim it first
# ...make the change in their source...
python3 $SK/uifb.py status fb-0003 done --note "Set .v to nowrap and clamped the font-size."
```

The note is not bookkeeping. It appears in the rail under the item, and it is
what lets the reviewer tell "done" from "done the way I meant".

If an item is wrong, unclear, or a bad idea, say so rather than half-doing it:

```bash
python3 $SK/uifb.py status fb-0007 wont_fix --note "This would break the mobile layout because ..."
python3 $SK/uifb.py note fb-0007 "Which of the two headers did you mean?"
```

Other commands you will want: `list [--status active|open|sent|done|all]`,
`show <id>`, `pending [--peek]` (claim what is waiting, when hooks are off),
`doctor`.

## Finding the code behind an item

In order of reliability:

1. `source:` in the briefing - Vue, Svelte and React dev builds leave the
   originating file on the DOM node. Trust it.
2. `scoped-style attribute:` - grep the `data-v-xxxxxxx` token to land on the
   right SFC.
3. The selector's test ids, ids and class names - grep those.
4. The screenshot plus the route - open the route's component and read.

The selector is recorded so *you* can find the code, and so the rail can jump
back to the element later. Do not paste it into the app as a hook for a fix.

## Reading a region item

A region carries a box, not an element. The briefing labels its selector
"element under the centre of the box" for a reason: the complaint is about the
area. Fixing the one element under the crosshair is the classic wrong move -
read the comment and the screenshot, and change what the sentence is about.

## Honesty rules

The reviewer trusts the ledger to say what really happened.

- Only mark `done` once the change is actually in their source. If you cannot
  verify it, say what you did and what you could not check, in the note.
- Never edit `.uifeedback/` by hand to make the list look better. It is the
  record of what they asked for.
- If an item turns out to need a decision only they can make, leave it
  `in_progress`, add a `note` with the question, and ask them directly too -
  a note alone can sit unread.

## Reference

- `references/architecture.md` - how the proxy, injection and store fit
  together, the item schema, and the HTTP API. Read before changing the tooling
  or debugging odd behaviour.
- `references/hooks.md` - what each hook event does, the loop-safety rule, and
  manual wiring for people who do not want `install-hooks` editing settings.
- `references/troubleshooting.md` - HTTPS targets, auth redirects, service
  workers, CSP, framework-specific notes, and what to do when the panel does
  not appear. Read this before improvising.

When the loop itself misbehaves, run the self-test before theorising - it
isolates tooling faults from setup mistakes:

```bash
python3 ~/.claude/skills/ui-feedback/scripts/selftest.py -v
```

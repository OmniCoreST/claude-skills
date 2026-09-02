# Hooks: how sent feedback reaches Claude

Without hooks the loop still works - the reviewer sends, and you pick items up
with `uifb.py pending` next time you are prompted. Hooks remove the "next time
you are prompted" part, which is the difference between the reviewer clicking
Send and the reviewer clicking Send *and then having to say something to you*.

## Wiring

```bash
python3 ~/.claude/skills/ui-feedback/scripts/uifb.py install-hooks
```

Writes to the project's `.claude/settings.json` (`--local` targets
`settings.local.json` instead, which suits a shared repo where the rest of the
team has not opted in). It is idempotent - re-running detects the existing
entries and changes nothing. Claude Code must be restarted, or `/hooks` run,
before the new settings load.

Manual equivalent, if editing settings yourself is preferred:

```jsonc
{
  "hooks": {
    "SessionStart": [{
      "matcher": "startup|resume|clear",
      "hooks": [{ "type": "command",
                  "command": "python3 \"/home/you/.claude/skills/ui-feedback/scripts/hook_uifb.py\"" }]
    }],
    "UserPromptSubmit": [{
      "hooks": [{ "type": "command",
                  "command": "python3 \"/home/you/.claude/skills/ui-feedback/scripts/hook_uifb.py\"" }]
    }],
    "Stop": [{
      "hooks": [{ "type": "command",
                  "command": "python3 \"/home/you/.claude/skills/ui-feedback/scripts/hook_uifb.py\"" }]
    }]
  }
}
```

## Scope: which settings file

`install-hooks` writes the project's `.claude/settings.json`; `--local` targets
`settings.local.json`; `--user` writes `~/.claude/settings.json` once and covers
every project. All three are detected, so `doctor`, the serve banner and the
rail agree about whether delivery is armed.

It refuses to run when the project root resolves to your home directory. That
happens when the command is run from `~` with no `.git` above it: the entries
would land in your *global* settings while the output claimed a project
install, and an unused `~/.uifeedback` would be left behind. Use `--user` when
covering everything is what you actually want.

## Which ledger the hook reads

Delivery only happens if the hook looks in the right place, and "the right
place" is not always the session's own directory. Resolution order:

1. **`UIFB_ROOT`** - an explicit path pins the session to that ledger and
   nothing else is consulted. This is how a session is aimed at a project it
   does not live in.
2. **The session's own project** - walking up from the payload's `cwd` for a
   `.uifeedback` ledger, as before.
3. **Any review server running right now** - a serving process records its root
   in `${XDG_STATE_HOME:-~/.local/state}/uifb/servers.json`, so a session
   working outside the reviewed checkout still receives what the reviewer sent.
   Those batches say which checkout they belong to, so the fix does not land in
   the wrong repo. Set `UIFB_CROSS_PROJECT=0` to switch this off.

Step 3 exists because step 2 alone fails silently in a very ordinary setup: the
reviewer marks up their app while the agent session runs somewhere else - a
home directory, a tooling repo, a sibling checkout. The hook walked up, found
no ledger, exited 0, and the reviewer watched a sent item sit there forever
with nothing to explain it. The workaround people reached for was a wrapper
script that rewrote the payload's `cwd` to a hardcoded path; `UIFB_ROOT` now
does that properly.

The registry is a cache of live processes, never a source of truth about
feedback. Every entry is re-checked before it is trusted - process alive, port
answering, ledger still on disk - and pruned when it is not, so a server that
was killed rather than stopped cannot keep delivering.

## What each event is for

Each answers a different "when would this otherwise be missed?".

**`SessionStart`** (`startup|resume|clear`) - you come back the next day.
Emits a one-line ledger summary, then a full re-briefing of everything still
`sent` or `in_progress`, whether or not a previous session was already told
about it. A fresh session has no memory of what an earlier one was handed;
carrying only a count would leave you knowing work exists but not what it is,
which is how unfinished items quietly become abandoned ones. Items already
`in_progress` are flagged as possibly half-applied, because that status means
some earlier session was interrupted mid-fix.

**`UserPromptSubmit`** - the reviewer sends while you are idle, then types
something unrelated. The pending batch arrives as context on that message
instead of waiting to be asked about.

**`Stop`** - the reviewer sends while you are mid-task. The hook exits 2 with
the briefing on stderr, which prevents the turn from ending and hands the text
back, so the fix happens now rather than after they notice nothing happened and
prod you.

Delivery uses `hookSpecificOutput.additionalContext` for the first two and exit
code 2 for `Stop`, per the hook contract.

## The loop-safety rule

A `Stop` hook that could serve the same batch twice would trap the session in a
loop that never ends.

The guarantee lives in the store, not in the hook script. `take_undelivered()`
selects items that are `sent` with no `delivered_at` **and stamps them** inside
one locked read-modify-write. An item can therefore block `Stop` exactly once.
If you ever change that function, keep the claim and the stamp in the same
locked write - splitting them reintroduces the loop.

Two more safeguards:

- The hook exits 0 immediately when `.uifeedback/feedback.json` does not exist,
  so it is silent in every project that has not opted in. A hook that chatters
  in unrelated repos is how people learn to delete hooks.
- Any unexpected exception is swallowed with exit 0. A broken feedback hook
  must never block a session.

Reopening an item from the rail clears `delivered_at`, which is what makes
"reopen" actually re-deliver.

## Checking it works

```bash
# does this project have them wired?
python3 ~/.claude/skills/ui-feedback/scripts/uifb.py doctor

# what would Stop hand back right now?
echo '{"hook_event_name":"Stop","cwd":"'"$PWD"'"}' \
  | python3 ~/.claude/skills/ui-feedback/scripts/hook_uifb.py; echo "exit=$?"
```

`exit=2` with a briefing means feedback is waiting. `exit=0` with no output
means nothing is - and is also what the second call must produce, since the
first one claimed the batch.

The rail's footer reads `hooksInstalled` from the server and phrases the Send
button's promise accordingly, so a reviewer is never told their feedback will
be picked up automatically when it will not be.

## Turning it off

Delete the three entries from `.claude/settings.json`, or set
`"disableAllHooks": true` for a blanket stop. Nothing else in the loop depends
on hooks - `uifb.py pending` claims waiting items by hand, and the ledger is
unaffected.

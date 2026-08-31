---
name: launch-website
description: Set up a complete self-service website system for a domain — an Astro site in a GitHub repo, deployed to Cloudflare Pages, with an automatic preview link on every proposed change, an optional Brevo-backed contact form, and a safety-checked Cloudflare DNS configuration. Use this whenever someone wants to launch, move, rebuild, adopt or hand over a website, including phrasings like "set up a new site for example.com", "convert our WordPress site", "put this site on Cloudflare Pages", "I want marketing to update the site without developers", "give me a preview link before it goes live", or "wire up my Astro project to a domain". Also use it when an existing Astro project needs hosting, preview deploys, a contact form, or a custom domain attached. Assume the person running it knows marketing and SEO but does not write code — every question and every error must be in plain language.
---

# Launch a website

You are setting up a system that lets a non-technical person maintain a website by
asking an AI for changes in plain language. Your job is the setup. Their job,
afterwards, is this loop:

1. Open Claude Code on the web, pick the repo, describe the change in normal words.
2. Ask for a **pull request** — a proposed change that has not gone live.
3. Wait ~2 minutes. A comment appears on it with a **preview link** — a private copy
   of the whole site with the change applied.
4. Check it. Happy → press **Merge pull request** and the real site updates in about
   two minutes. Not happy → say what to fix, or close it and nothing ever happened.

Everything you build exists to make that loop work and make it safe. The preview link
is the heart of it: it is what lets someone who cannot read code change a live site
without fear.

## Who you are talking to

Assume marketing and SEO fluency, zero code fluency. That means:

- **Never use a technical term without defining it in the same breath.** "a pull
  request (a proposed change that isn't live yet)". Once defined, use it freely —
  they will see the word on GitHub's buttons and need to recognise it.
- **Name the button.** Not "merge the PR" but "press the green **Merge pull request**
  button, then **Confirm merge**".
- **Never paste a raw error.** Translate it, then say what you are doing about it.
  "Cloudflare says that name is taken — I'll use `acme-web` instead" beats a JSON blob.
- **Say what a change means for visitors before you make it**, not what it means
  technically. "For about a minute, people typing your address might not reach the
  site" is useful. "Updating the apex A record" is not.
- **Ask in small batches.** Group the independent questions into one short numbered
  list they can answer in a single reply. Ask branching questions one at a time.

Words worth avoiding entirely unless you define them: commit, branch, DNS propagation,
nameserver (define as "the service that tells the internet where your website and
email live"), CNAME, apex, adapter, SSR, build step, environment variable.

## Non-negotiable safety rules

These exist because each one has already caused a real outage or near-miss.

**Email is not yours to touch.** A domain's mail routing lives in the same place as its
website settings, so you will be looking straight at it the entire time. Never create,
change or delete an `MX` record, an `SPF` record (a `TXT` starting `v=spf1`), a DKIM key
(anything under `_domainkey`), a `_dmarc` record, or any ownership-verification `TXT`
(`google-site-verification`, `MS=`, `brevo-code`, and similar) unless the person has
explicitly asked for that specific record, in this conversation, after you explained
what breaks. Deleting a verification record silently un-verifies the domain with a
provider; changing a DKIM key breaks the signature on mail already in flight. Neither
fails loudly. Both surface days later as "our email stopped working".

**Show every DNS change before making it, and make them one at a time.** Print the
record's current value, the new value, and one plain sentence about what a visitor
would notice. Wait for a yes. A blanket "go ahead, fix everything" earlier in the
conversation does not cover a record you are about to touch now.

**Never guess a domain's list of names.** DNS cannot be enumerated by asking it
questions — a name you do not think to ask about is invisible, not absent. This exact
mistake took four subdomains offline in the project this skill is generalised from.
Build the list from several independent sources and reconcile them. `references/dns.md`
has the method.

**Dry run, then apply.** Anything that changes DNS or deletes files gets shown as a
preview first. If you write a script, give it a `--dry-run` flag and use it.

**Nothing reaches the live site except by merging a pull request.** Do not run
`wrangler pages deploy` by hand after the workflow exists, and do not push to `main`.
The one exception is the very first deploy, before any content exists to break.

## Phase 0 — Preflight

Run `scripts/preflight.sh`. It reports what is installed and what is signed in. Work
through whatever it flags before asking the person anything, so the interview is not
interrupted by tooling problems.

Requirements: Node 20+, `git`, `gh` (GitHub CLI) signed in with `repo` **and**
`workflow` scope — without `workflow` the push of the deploy file is rejected with a
confusing error — plus `jq` and `curl`. Wrangler is used via `npx wrangler`, no install
needed.

Two credentials come from the person, and both need walking through:

- **A Cloudflare API token** for the deploy. `references/cloudflare.md` has the exact
  click path and the permissions to tick.
- **A second Cloudflare API token, scoped to the one domain**, if DNS work is needed.
  This is separate on purpose. See the warning below.

> **`wrangler` cannot manage DNS records.** Its sign-in gives read-only access to zone
> settings, so any attempt to write a DNS record fails with a permissions error. There
> is no `wrangler dns` command and no `wrangler pages domain` command. DNS records and
> custom-domain attachment both go through the Cloudflare REST API with a scoped token.
> Do not spend time looking for a wrangler subcommand that does this — it does not exist.

## Phase 1 — Interview

Read `references/interview.md` and follow it. It has the exact wording for each
question, what each answer is used for, and which follow-ups are conditional.

Ask the four essentials as one numbered list: **web address**, **GitHub location**,
**starting point**, **languages**. Then branch based on the starting point.

Before moving on, play the answers back as a short summary and get a yes. Setup takes
a while and a wrong domain or repo name is expensive to unwind later.

## Phase 2 — Get the site into `web/`

Three starting points, three reference files. Read only the one that applies.

| They said | Read | You produce |
|---|---|---|
| Build something new | `references/build-new.md` | A fresh Astro site from their description |
| Copy our current site | `references/build-from-url.md` | A faithful port of the live site, URLs preserved |
| I already have one | `references/build-from-existing.md` | Their project moved into the expected shape |

All three converge on the same layout, which the rest of the skill assumes:

```
<repo>/
├── README.md, AGENTS.md, CLAUDE.md, GEMINI.md, EDITING.md
├── .github/workflows/deploy.yml
└── web/                    ← the npm project lives here, not at the root
    ├── package.json, astro.config.mjs
    ├── functions/api/contact.js       (only if there is a contact form)
    ├── public/
    └── src/
```

The `web/` subfolder is not decoration. The deploy file runs its build steps with
`working-directory: web`, and Cloudflare picks up `web/functions/` as the site's API
routes purely because they sit next to the built output. Keep the shape.

Whatever the starting point, the site must build as **static output with no adapter**.
Do not add `@astrojs/cloudflare`. The one dynamic piece is the contact form, and it
lives outside the Astro build entirely as a Cloudflare Pages Function. Adding an
adapter switches the whole site to server rendering and breaks this arrangement.

Confirm `npm run build` succeeds inside `web/` before going further.

## Phase 3 — Wire up the repo

Copy the four templates from `assets/`, substituting the placeholders (each file lists
its own at the top):

| Template | Goes to | Purpose |
|---|---|---|
| `deploy.yml.template` | `.github/workflows/deploy.yml` | The build + preview-link mechanism |
| `AGENTS.md.template` | `AGENTS.md` | House rules the AI reads on every future change |
| `EDITING.md.template` | `EDITING.md` | The plain-language guide for the person |
| `headers.template` | `web/public/_headers` | Security headers |

Then write `CLAUDE.md` and `GEMINI.md`, each containing exactly one line:

```
All project rules live in [AGENTS.md](AGENTS.md) — read that file and follow it.
```

Three files rather than one because different assistants look for different names, and
duplicating the rules three ways guarantees they drift apart.

`AGENTS.md` is the highest-leverage file you write. It is what stops a future AI from
inventing a customer count, translating only one language, or restyling a page nobody
asked it to touch. Fill in real editorial rules from what you learned in the interview
— the template's placeholders are prompts to think, not text to ship.

Create the repo if it does not exist (`gh repo create`), ask first, and default to
**private** unless they say otherwise. Push `main`.

## Phase 4 — Cloudflare Pages

Read `references/cloudflare.md`. In short: create the Pages project, add the API token
to the repo as a secret named `CLOUDFLARE_API_TOKEN`, do one first deploy, and confirm
the `.pages.dev` address works.

Then prove the loop works end to end **before** touching the domain — open a trivial
pull request, confirm the preview comment appears with a working link, and merge it.
If this does not work, nothing else matters, and it is far easier to debug now than
after DNS is in play.

## Phase 5 — Contact form

Only if they said yes. Read `references/brevo.md`.

The one thing that catches everyone: **the "from" address must be registered in Brevo
as a sender.** Having the domain verified is not enough on its own. Brevo accepts the
send request for an unregistered sender, returns success, and then silently drops the
message — so the website reports "sent" and nothing ever arrives. If a test message
does not turn up, check sender registration first.

## Phase 6 — The domain and DNS

Read `references/dns.md` in full before touching anything. This is the phase that can
break email, and the reference exists because these mistakes have already been made
once.

The shape of it: find out where the domain's DNS actually lives; audit every record and
sort it into *mail*, *verification*, *website*, *other*; change only the website ones;
show each change and get a yes; verify afterwards from several public resolvers rather
than trusting the local one.

If DNS is not on Cloudflare yet, guide the move — add the domain, check the imported
records against the current ones, hand over the two nameserver addresses to set at the
registrar, then wait and verify before continuing. Do not delete anything until the old
nameservers have stopped answering, because until then there are two live copies of the
settings and you are only editing one.

## Phase 7 — Hand over

Read `references/handover.md`. Produce:

- A finished `EDITING.md` in the repo, naming their actual repo and addresses.
- A short handover message covering: where the site lives, how to change it, how to
  undo a change, who to contact, and the one or two site-specific quirks worth knowing.
- The list of anything still outstanding, said plainly.

Then walk them through one real change, start to finish, while you are still there.
Reading the loop and doing the loop are different things, and the first solo attempt
should not be the first attempt.

## Keep notes as you go

Setup spans a lot of steps and the person may leave and come back. Keep a running
`SETUP-NOTES.md` in the working directory: their answers, what is done, what is next,
and any decision with a reason. Update it at the end of each phase.

If this skill starts and `SETUP-NOTES.md` already exists, read it first and resume from
where it stopped rather than re-interviewing.

Do not put secrets in it. Record "Brevo key added to the Pages project", never the key.

## References

Read these as you reach the phase that needs them, not up front.

| File | When |
|---|---|
| `references/interview.md` | Phase 1 — the questions, in order, with exact wording |
| `references/build-new.md` | Phase 2 — building a site from scratch |
| `references/build-from-url.md` | Phase 2 — porting a live site, including WordPress |
| `references/build-from-existing.md` | Phase 2 — adopting an existing Astro project |
| `references/cloudflare.md` | Phase 4 — tokens, Pages project, custom domains, API cookbook |
| `references/brevo.md` | Phase 5 — contact form and mail sending |
| `references/dns.md` | Phase 6 — the DNS safety doctrine. Read fully before any DNS change |
| `references/handover.md` | Phase 7 — what to hand over and how to explain it |

`scripts/preflight.sh` checks tooling. `scripts/dns-audit.sh` reads a Cloudflare zone
and classifies every record by risk — it only reads, never writes.

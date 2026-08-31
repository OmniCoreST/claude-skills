# Adopting an existing Astro project

They already have the site. You are adding the system around it — the deploy pipeline,
the preview links, the docs, and possibly the form and domain.

The bias here is strongly towards **changing as little as possible**. It is their
project, it presumably works, and every change you make is one they did not ask for and
will have to understand later.

## Look before touching

```bash
cd <their-project>
cat package.json
cat astro.config.* 2>/dev/null
ls -la
git log --oneline -10 2>/dev/null
npm ci && npm run build
```

Answer these before proposing anything:

- Does it build? If not, fix that first — nothing else can be verified until it does.
- Is it version controlled already, and does it have a remote?
- Is there an adapter configured?
- Where does the built output land — `dist/` or somewhere else?
- Are there already functions, API routes, or environment variables in use?
- Is anything secret committed? Check before pushing anywhere.

## The two structural questions

### Is `web/` needed?

The system expects the npm project at `web/` inside the repo, with docs and the workflow
at the root. If theirs sits at the repo root instead, you have a choice:

**Move it** if the repo is theirs alone and the history is short. Cleaner, and matches
every other site set up this way.

```bash
mkdir web && git mv <each item> web/     # git mv, so history follows
```

**Leave it** if the repo has real history, other contributors, or anything else in it.
Adjust the workflow instead — it is three lines:

```yaml
cache-dependency-path: package-lock.json   # was web/package-lock.json
working-directory: .                       # was web  (both install and build steps)
workingDirectory: .                        # was web  (the wrangler step)
```

Ask which they prefer, in terms of consequence rather than layout:

> Your project sits at the top of the folder. I can either move it into a `web/`
> subfolder — which matches how the other sites are set up and keeps the instructions
> identical — or leave it where it is and adjust the deploy settings instead. Both work.
> Moving is tidier; leaving it alone is safer if anyone else works on this.

### Is there an adapter?

If `astro.config.*` has `output: 'server'`, `output: 'hybrid'`, or an adapter import,
the site is server-rendered and this setup does not fit as written.

Do not silently rip it out — it may be there for a reason. Find out:

```bash
grep -rn "Astro.request\|export const prerender\|export async function (GET|POST)" src/ | head -30
```

- **Nothing found** — the adapter is probably left over from a template. Offer to remove
  it and go static, explaining that it makes hosting simpler and the site faster. Their
  call.
- **Real server-side code found** — the site genuinely needs a server. Say so plainly:
  the preview-and-merge workflow still works, but deployment targets Cloudflare Workers
  rather than static Pages and the contact-form arrangement in this skill does not
  apply. Do not pretend otherwise, and do not convert their working code to fit.

## Add without disturbing

Everything the system needs is additive:

```
+ .github/workflows/deploy.yml
+ AGENTS.md, CLAUDE.md, GEMINI.md, EDITING.md
+ web/functions/api/contact.js       (only if they want a form)
+ web/public/_headers                (only if absent)
```

Before writing each one, check whether it exists:

- **An existing `AGENTS.md` or `CLAUDE.md`** — read it and merge. Their rules win; add
  the workflow section (never push to main, always open a pull request, build must pass)
  without overwriting anything of theirs.
- **An existing workflow** — do not add a second thing that deploys. Read what is there.
  If it already deploys somewhere, that is a conversation about replacing it, not
  something to do quietly.
- **An existing `_headers`** — leave it. Suggest additions if security headers are
  missing, but do not overwrite a file someone wrote deliberately.
- **An existing `robots.txt` or `sitemap`** — leave both alone.

## Check `site` is set

```js
export default defineConfig({
  site: 'https://example.com',   // must be the real address
});
```

Frequently missing or still pointing at a placeholder from whatever template it started
as. It is what canonical URLs, `hreflang` and the sitemap are built from, so a wrong
value tells search engines the site lives somewhere it does not. Worth checking even
though it is not strictly part of the setup — and worth mentioning, since they will care.

## A quick look at the site itself

You are not there to review their code, but a few things are cheap to check and
genuinely useful to someone who cares about SEO. Mention what you find; fix only what
they ask for:

- Pages with a missing, duplicated, or empty `<title>` or `<meta name="description">`.
- No canonical URL.
- Multiple languages without `hreflang`.
- No sitemap, or one not referenced from `robots.txt`.
- Images with no `alt` text.

Offer it as a short list, not a lecture:

> While I was in there I noticed three pages share the same description and there's no
> sitemap. Neither affects the setup — want me to fix them while I'm here, or leave them
> for later?

## Before moving on

- `npm run build` passes.
- Build output is `dist/`, or the workflow points at wherever it actually goes.
- Nothing secret is committed. Check `.env`, `.dev.vars`, and anything with a key in it,
  and make sure `.gitignore` covers them.
- Their existing conventions survived — the diff contains what you added and nothing you
  reformatted.

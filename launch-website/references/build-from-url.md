# Porting a live site

They have a site and want the same site, in the new system. The commonest case is
WordPress, but the method is the same for anything.

**A port is not a redesign.** The result should look like the site they know. They can
ask for design changes afterwards, one at a time, with a preview link — which is a far
better experience than being handed something unrecognisable and asked to approve it.
Say this at the start, and again if you are tempted to improve something.

If they *do* want a redesign, that is a different job: port first, deploy, then redesign
as a separate change with its own preview. Two changes at once means that when something
looks wrong, nobody can tell which change caused it.

## Survey first

Before writing anything, find out what you are dealing with, and report it back.

```bash
curl -s https://example.com/sitemap.xml | grep -o '<loc>[^<]*' | sed 's/<loc>//'
curl -s https://example.com/robots.txt
curl -sI https://example.com | head -20          # server, platform hints
```

Establish:

- **How many pages**, and their addresses. The sitemap first; crawl the navigation if
  there isn't one.
- **How many languages**, and how the URLs distinguish them (`/tr/`, `?lang=tr`, a
  subdomain, or a session — the last cannot be reproduced statically and becomes a real
  decision).
- **What is dynamic** — a search box, a login, a shop, a booking form, a comment
  section. A static site cannot do these. Find out now.
- **How big the media is.** A site with 500 MB of images needs a conversation, not a
  silent `git add`.

Report it plainly and get agreement on scope:

> Your site has 21 pages in three languages, plus 30 product photographs and six PDF
> brochures. Everything is straightforward except the search box in the header, which
> needs the old system to work. I'd suggest removing it — the site is small enough to
> navigate — but tell me if you'd rather keep search and we'll find another way.

## Mirror the site

Take a local copy to work from, so you are parsing the same bytes every time rather than
a site that might change under you:

```bash
wget --mirror --page-requisites --adjust-extension --no-parent \
     --domains=example.com \
     --reject-regex='(wp-admin|wp-login|xmlrpc|\?replytocom|/feed/|/comments/feed/)' \
     https://example.com/
```

**macOS has no `wget`.** Install it with `brew install wget`, or mirror with curl
instead — slower to write, but always present:

```bash
# one page at a time, from a list of URLs you already have
xargs -n1 -P4 curl -sS --create-dirs -o '#1' --path-as-is < urls.txt
```

Getting `wget` is usually worth the two minutes; its `--page-requisites` handling of
images, CSS and fonts is the part that is tedious to reproduce by hand.

Then check the file count against the page count you expected. A mismatch means the
crawl missed something or followed something it shouldn't have.

## Extract content into data, not markup

The single most important decision. Pull the text out of the mirrored HTML into one
structured file per language, and render it through Astro components.

```
web/src/i18n/content.json     { "en": {...}, "tr": {...}, "fr": {...} }
web/src/i18n/content.ts       types + accessor over it
```

Keys must be **identical across languages**, and the languages must sit side by side in
one file. That is what makes it hard for a future change to update English and forget
Turkish — they are three lines apart, not three files apart.

Keep paths language-neutral in the data (`"path": "/quality-policy"`) and prefix at
render time, so only the words differ per language.

Where the original has rich formatting — a product description with lists and links —
storing it as a trusted HTML string is legitimate and much simpler than modelling every
tag. Make it an explicit rule in `AGENTS.md`: site-authored HTML only, never third-party
or visitor-supplied markup, never a `<script>` tag.

## Keep the URLs

This is the part where SEO is won or lost, and the person will care about it more than
anything else you do.

**Every page must keep the address it has today.** A URL that changes loses whatever
ranking it had, along with every inbound link and bookmark pointing at it.

That includes URLs that are *wrong*. If the old site has `/projectcat/advance-metering-software`
for a page about something else entirely, keep it. It has been indexed for years. Fixing
it costs real traffic and gains nothing. Write this into `AGENTS.md` explicitly, with
the reason, or a future AI will helpfully "correct" it.

Match the old URL shape in Astro's config:

```js
trailingSlash: 'ignore',        // when the old site served both forms
build: { format: 'directory' }, // /about/index.html  → /about/
// or
build: { format: 'file' },      // /about.html        → /about
```

Where a URL genuinely must change, add a permanent redirect in `web/public/_redirects`:

```
/old-path/*   /new-path/:splat   301
/en/*         /:splat            301
```

Use `301`, not `302` — the move is permanent and search engines should transfer the
ranking rather than keep checking back.

Deliberately let dead platform paths 404, and say why in a comment. `/wp-admin/`,
`/wp-login.php` and `/wp-json/*` should not redirect anywhere: they are gone, and
guarding paths that no longer exist just advertises what the site used to be.

## Assets

Copy images, fonts and documents to `web/public/` **under their original paths**. If a
stored description says `<a href="/wp-content/uploads/2023/04/leaflet.pdf">`, that file
needs to be at that path, or you are rewriting every link by hand and missing some.

Strip the query strings a crawler bakes into filenames
(`fontawesome-webfont78ce.woff?v=4.2.0` → `.woff`) or the references will not resolve.

If the site's CSS and JavaScript are a theme you are reproducing, copy them verbatim and
do not reformat them. They are not yours to tidy, and a diff full of whitespace changes
hides the one real change inside it.

Check the total size before committing. Above ~100 MB, raise it — Git handles large
binaries poorly and it will slow every future change.

## Reproduce, don't improve

You will find things that look like bugs. Some are load-bearing. Before "fixing"
anything, ask whether the live site depends on it.

Keep a section in `AGENTS.md` — *Looks wrong / Why it is right* — listing each one, or
the next AI to read the code will fix them all again:

| Looks wrong | Why it is right |
|---|---|
| A misspelled element id in the navigation | The theme's JavaScript selects on it |
| Product page titles cut off mid-word | Matches the live site; changing them changes the `<title>` |
| An old jQuery loaded before everything else | Later scripts assume it is already there |
| A heading in the wrong language on a translated page | The original does this; fixing it is a content decision, not a port decision |

This file is the difference between a port that survives and one that decays.

## Verify against the original

Write a script that checks the built output against what the live site actually serves.
Doing this by eye across 21 pages in 3 languages does not work.

Check, per page: the `<title>`, the `lang` attribute, the number of `hreflang` links,
every navigation label, the main headings and body text, that every image and document
link returns 200, that the contact form points at `/api/contact`, and that no leftover
platform artefact (`var wpcf7 =`, admin links) survives.

Exit non-zero on any failure. Run it before the first deploy and keep it in the repo —
it is also the regression test for every future change.

## What cannot come across

Be direct about these rather than discovering them at handover:

| Old feature | Reality |
|---|---|
| Search | Needs a server. Remove it, or add a hosted search service later. |
| Comments | Needs a server. Usually nobody misses them. |
| Login / member area | Out of scope. Keep it on the old system or plan separately. |
| Shop / cart | Out of scope. Use a hosted checkout. |
| Contact form | **Does** carry across — as a Pages Function. See `brevo.md`. |
| Language switching by session | Becomes URL-based (`/tr/`). Better for SEO anyway. |

## Turning off the old site

Not yet. Leave it running until the new one is live on the real domain and has been
checked. Then keep it available but unreferenced for a while.

Before anything is switched off, confirm: everything is committed, the media is all
present, and anything that only existed in the old system's admin area — form
submissions, uploaded files not linked from any page — has been exported. Once the old
hosting is cancelled, whatever was only there is gone.

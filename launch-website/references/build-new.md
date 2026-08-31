# Building a new site

You have their answers from the interview: what the company does, who for, what
visitors should do, which pages, which languages. Now build something real.

## Scaffold

```bash
mkdir -p <repo>/web && cd <repo>/web
npm create astro@latest . -- --template minimal --no-install --no-git --typescript strict
npm install
```

Then trim what the template adds and does not earn. The reference sites run on a
deliberately small dependency list — Astro alone in two cases. Every dependency is
something that can break a build two years from now, in a repo whose owner cannot read
the error.

Add only what you will actually use:

```bash
npm i @astrojs/sitemap          # yes — SEO, and it costs nothing
npm i @astrojs/tailwind tailwindcss@^3   # only if you are styling with Tailwind
```

**Do not add an adapter.** No `@astrojs/cloudflare`. The site is static; the contact
form is a Pages Function outside the build. An adapter switches on server rendering and
breaks that arrangement.

## `astro.config.mjs`

```js
import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';

export default defineConfig({
  site: 'https://example.com',
  trailingSlash: 'always',
  integrations: [sitemap({ changefreq: 'weekly', lastmod: new Date() })],
  build: { inlineStylesheets: 'auto' },
  // only when there is more than one language:
  i18n: {
    defaultLocale: 'en',
    locales: ['en', 'tr'],
    routing: { prefixDefaultLocale: false },
  },
});
```

`site` must be the real address — it is what canonical URLs and the sitemap are built
from. Getting it wrong tells search engines the site lives somewhere it does not.

## Structure

```
web/src/
  consts.ts              site name, url, email, nav, social — one source of truth
  i18n/ui.ts             every visible string, per language
  layouts/BaseLayout.astro   the only layout: head, meta, SEO, header, footer
  components/            one per section; pages assemble them
  pages/                 index.astro, about.astro, contact.astro, 404.astro
                         tr/index.astro, tr/about.astro, ...   (one shim per language)
```

**Put text in `i18n/ui.ts`, not in the markup.** The whole system depends on a future AI
reliably finding the sentence someone asked to change. A typed dictionary makes that a
lookup; text scattered through templates makes it a search that can miss a copy.

Type the dictionary so a missing translation is a build error rather than a silently
English page:

```ts
export interface Strings {
  htmlLang: string;
  nav: { home: string; about: string; contact: string };
  hero: { heading: string; body: string; cta: string };
  /* … */
}
export const ui: Record<Lang, Strings> = { en: { /* … */ }, tr: { /* … */ } };
export const useTranslations = (lang: Lang) => ui[lang];
```

## Multiple languages

The pattern that works: **all markup lives once in `components/`; the files under
`pages/` only bind a language to it.** Each localised page is a shim:

```astro
---
import HomePage from '../../components/HomePage.astro';
---
<HomePage lang="tr" />
```

One helper owns the URL rule, and nothing else builds paths by hand:

```ts
/** The first language sits at the root; the others are prefixed. */
export function localizePath(path: string, lang: Lang): string {
  const clean = path === '/' ? '' : path.replace(/\/$/, '');
  return lang === DEFAULT_LANG ? clean || '/' : `/${lang}${clean}` || '/';
}
```

Components take a **language-neutral** path (`/about`) and localise at render time. That
is what makes a language switcher land on the same page in the other language instead of
dumping the visitor on the home page.

## SEO

They know this subject better than you do — do it properly and they will notice.

Everything goes in `BaseLayout.astro`, driven by props, so no page can forget it:

- `<title>`, unique per page. Append the site name only when it still fits in ~62
  characters, so search results are not truncated mid-word.
- `<meta name="description">`, unique per page, ~150–160 characters. Never ship it empty.
- `<link rel="canonical">` — the absolute URL of this page.
- `hreflang` for each language plus `x-default`, built from the neutral path so every
  version cross-references every other, itself included.
- Open Graph and Twitter card tags — `og:title`, `og:description`, `og:image`
  (1200×630), `og:url`, `og:type`, `twitter:card=summary_large_image`.
- JSON-LD: `Organization` on the home page, `BreadcrumbList` on inner pages, and
  whatever else genuinely applies. Do not invent structured data for things the company
  does not have.
- The sitemap comes from the integration. Reference it in `robots.txt`.

`web/public/robots.txt`:

```
User-agent: *
Allow: /

Sitemap: https://example.com/sitemap-index.xml
```

## Writing the content

You are drafting copy for a company you just learned about in one paragraph. Two rules,
both of which go into `AGENTS.md` as permanent editorial rules:

**Never invent a fact.** No customer counts, client names, years in business,
certifications, standards compliance, accuracy figures, awards, partnerships, or
uptime numbers. In a regulated or technical industry a wrong specification is a
commercial and legal problem, not a typo. When a number would be natural and you do not
have it, write the sentence without it and flag it for them to fill in.

**Mark what you invented.** Anything you drafted rather than were told is a placeholder.
List them at handover so nothing fictional quietly becomes the company's public claim.

Prefer a shorter honest site to a longer padded one. Empty superlatives are also the
easiest thing for them to improve later once the system is running.

## Before moving on

- `npm run build` passes in `web/`.
- Every page has a unique title and description.
- Every language has every page, with no half-translated pages.
- No invented facts, and placeholders listed.
- Contact details are the real ones from the interview.

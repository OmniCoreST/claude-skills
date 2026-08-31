# The interview

Wording matters here. The person knows what a domain is, what SEO is, and what they
want the site to say. They do not know what a repository is, and asking them to "pick a
package manager" will lose them.

Two principles:

- **Every question states what the answer is used for.** People give better answers
  when they know what turns on them, and it stops the interview feeling like a form.
- **Every question has a way forward if they don't know.** "I don't know" is a common
  and reasonable answer. Have a default ready and say what it is.

Ask the four essentials as one numbered list they can answer in a single reply. Then
branch. Do not ask about anything you can find out yourself — look first.

---

## The four essentials

Ask these together.

### 1. Web address

> **What web address will the site live at?**
> Just the domain, without `https://` — for example `example.com`. If it should also
> work with `www.` in front, say so; setting up both is normal and I'll assume you want
> it unless you say otherwise.

Used for: the Pages project name, the address written into the site so search engines
know the canonical location, the sitemap, and the DNS work in Phase 6.

If they don't have a domain yet: the site can be built and published on a free
`.pages.dev` address today and pointed at a real domain later, with no rework. Offer
that rather than stalling.

### 2. GitHub location

> **Where should the site's files live on GitHub?**
> Give it as `account/name` — for example `acme-marketing/web-example`. This is the
> page you'll open whenever you want to change something, and it's where the preview
> links appear. If it doesn't exist yet I'll offer to create it.

Used for: everything. This is where the person will spend their time afterwards.

If they don't know: suggest `<their-github-username>/web-<sitename>`. Run
`gh api user --jq .login` to get the username rather than asking. Check whether they
belong to any organisations (`gh api user/orgs --jq '.[].login'`) and offer those too —
a company site usually belongs in the company account, not a personal one, and moving
it later is a nuisance.

### 3. Starting point

Use a choice question for this one. Three options, and be concrete about the work each
implies:

> **Where are we starting from?**
>
> - **A new site** — there's nothing yet. You tell me what the company does and I write
>   the pages.
> - **Copy the site you have now** — give me its address and I rebuild it in the new
>   system, keeping the text, images and page addresses as they are.
> - **A site you already have as files** — you already have an Astro project somewhere
>   on this computer. Tell me the folder.

Determines which of `build-new.md` / `build-from-url.md` / `build-from-existing.md`
to read in Phase 2.

If they picked *copy the site you have now*, ask for the address immediately and open
it before continuing — what you find changes the rest of the conversation, and it is
better to discover a 40-page site now than in Phase 2.

### 4. Languages

> **Which languages should the site be in?**
> Name them in order of importance. The first one sits at the plain address
> (`example.com/about`); the others get a short prefix (`example.com/tr/about`), which
> is what search engines expect and what tells them these are the same page in another
> language.
>
> Adding a language later is possible but means revisiting every page, so it's worth
> settling now even if the other languages come later.

Used for: the site structure, and a rule in `AGENTS.md` that a text change is only half
done until it is made in every language.

If they name more than one, add this to `AGENTS.md` as a numbered editorial rule, in
their words: *"A text change is not finished until the same change is made in all N
languages. Never leave the main language sitting in place as a placeholder — ask rather
than guess, especially for industry vocabulary."* Machine-translated technical terms in
a specialist industry are worse than an honest gap.

---

## Then, conditionally

### Contact form

> **Should the site have a contact form that emails you when someone fills it in?**

If yes, two follow-ups — and explain the second, because it is genuinely confusing:

> **Which address should receive the messages?** — for example `info@example.com`.
>
> **Which address should they appear to come from?** A website can't send email by
> itself, so it hands the message to a mail service (Brevo — free for this amount of
> use). That service needs a "from" address that you've confirmed you own. It is
> usually simplest to use the same address that receives them.

Phase 5 and `references/brevo.md` handle the rest. Do not ask for the Brevo API key
here — it comes later, at the point it is actually used, so it isn't left sitting in
the conversation.

Also offer spam protection, but do not push it:

> Contact forms attract automated spam. The site includes an invisible trap that
> catches most of it with no effect on real visitors. If the form gets a lot of traffic
> we can add a stronger check later — it's a small change, and not worth doing now
> unless you already know spam is a problem.

### Who to contact

> **If someone gets stuck with the site later, who should they ask?**
> A name and an email address. It goes at the bottom of the instructions.

### For a new site only

Ask these only in the *new site* branch — they are meaningless for a port. They are
also the questions this person is best qualified to answer, so it is worth spending
their time here rather than on technical detail:

> - **In one sentence, what does the company do, and for whom?**
> - **What should someone do when they arrive?** Call, request a quote, download a
>   brochure, book a demo?
> - **What pages do you need?** Home plus a handful is normal — About, Products,
>   Contact. More can be added any time.
> - **What should the home page's title and description be in search results?** If you'd
>   rather I draft them from the above, I will.
> - **Do you have a logo, brand colours, or photographs to use?** If not, I'll build it
>   plain and legible and we can style it once you do.

---

## Before you move on

Play it back. Short, and in their terms — not a config dump:

> Here's what I'm setting up. Tell me if anything is wrong before I start.
>
> - **example.com**, also answering at www.
> - Files at **acme-marketing/web-example** on GitHub (I'll create it, private).
> - **English and Turkish**, English at the plain address.
> - A **contact form** to info@example.com.
> - A **new site**: home, about, products, contact.
>
> This takes 20–30 minutes. I'll check with you before anything becomes visible to the
> public, and again before I change anything to do with the domain.

Wait for confirmation. Then write it all into `SETUP-NOTES.md` before starting work.

---

## Things to find out rather than ask

Look these up yourself. Asking wastes their time and invites a wrong answer:

| Fact | How |
|---|---|
| GitHub username / orgs | `gh api user --jq .login`, `gh api user/orgs --jq '.[].login'` |
| Whether the repo exists | `gh repo view <owner>/<name>` |
| Whether the domain's DNS is on Cloudflare | `dig +short NS <domain>` |
| Who the domain is registered with | `whois <domain>` |
| Whether a Pages project already exists | `npx wrangler pages project list` |
| What the current site looks like | Fetch it |
| What pages the current site has | Its `sitemap.xml`, then crawl |
| Whether the domain already sends email | `dig +short MX <domain>` and the SPF record |

That last one matters more than it looks. A domain with live `MX` records is a domain
where someone's email is running right now, and everything in Phase 6 gets more careful.
Check it early, and say so plainly when you get there: *"This domain is handling live
email, so I'm going to leave everything mail-related alone and only touch the website
settings."*

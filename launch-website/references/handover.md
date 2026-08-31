# Handing over

Setup is not finished when the site is live. It is finished when the person can change
it without you.

## Final checks

Walk these yourself before saying anything is done:

- [ ] The live domain loads over HTTPS, with and without `www`.
- [ ] The certificate covers both forms (no browser warning on either).
- [ ] Every page loads; no broken images or links.
- [ ] `robots.txt` and the sitemap are reachable, and the sitemap lists every page.
- [ ] Every page has a unique title and description.
- [ ] Each language is complete, with `hreflang` linking the versions.
- [ ] The contact form sends, and the message arrives — tested on the **live** site.
- [ ] The reply-to address on the received message is the person who filled the form in.
- [ ] A test pull request produced a working preview link, and merging it updated the
      live site.
- [ ] Old URLs still resolve, or redirect (`curl -sI` a few of the important ones).
- [ ] Nothing secret is committed. Check `.env`, `.dev.vars`, and the git history.
- [ ] `EDITING.md` names the real repo, addresses and contact — no placeholders left.

## The handover message

Short, specific, and in their language. Something like:

> **{{SITE_DOMAIN}} is live.**
>
> **To change anything:** open <https://claude.ai/code>, pick the `{{REPO}}` repository,
> and describe what you want in normal words. Ask it to open a pull request, wait about
> two minutes for the preview link in the comments, check it, then press **Merge pull
> request**. Full instructions are in `EDITING.md` in the repository.
>
> **To undo anything:** open the merged pull request, press **Revert**, merge that.
>
> **Two things worth knowing:**
> - The contact form doesn't work on preview links — only on the live site. That's
>   deliberate.
> - Some office networks block preview links. Try a phone on mobile data if one won't
>   open.
>
> **Still outstanding:** [list, or "nothing"]
>
> **If you get stuck:** {{OWNER_NAME}}, {{OWNER_EMAIL}}

## Do one change together

The most valuable ten minutes of the whole setup. Reading the loop and doing the loop
are different things, and the first solo attempt should not be the first attempt.

Pick something real and trivial — a phone number, a sentence on the About page. Then
have **them** drive while you watch:

1. They open Claude Code and describe the change.
2. They ask for a pull request.
3. They find the preview link in the comment.
4. They check the change on the preview.
5. They merge it.
6. They see it live.

Do not do it for them. If they get stuck, note where — that is a gap in `EDITING.md`,
and fixing it is worth more than any other edit you could make to that file.

Then have them revert it, so they have used the undo button once while someone was
watching. People are far braver with a system whose undo they have personally tested.

## Say what is still outstanding

Plainly, with consequences and rough timing. Things that commonly remain:

| Item | Say it like this |
|---|---|
| DNS still moving | "Some people may still reach the old site for up to a day. Nothing to do — it settles by itself." |
| Old hosting still running | "Still paying for the old host. Safe to cancel once you're happy — I'd give it two weeks." |
| Placeholder content | "These sentences I drafted from what you told me — worth a read: [list]" |
| Search Console not set up | "Worth adding the site to Google Search Console so you can see how it's found." |
| No analytics | "There's no visitor tracking. Cloudflare's is free and doesn't need a cookie banner." |
| Turnstile not enabled | "Basic spam protection only. If spam starts arriving, tell me and it's a small change." |
| DNS token still active | "You can delete the DNS token in Cloudflare now — it was only needed for setup." |

## Clean up

- Delete the test branch and any test pull requests.
- Remove scaffolding files you created and did not use.
- Tell them to delete the DNS API token; the deploy token stays.
- Update `SETUP-NOTES.md` to a final state and leave it in the repo. It is the record of
  what was decided and why, and the next person to touch this — possibly you, in a
  year — will want it.

## If something is genuinely unfinished

Say so directly. Do not round a partial result up to a finished one.

A person who is told "the site is live but the contact form is waiting on your Brevo
confirmation email" can act on it. A person told "all done" discovers it themselves,
later, from a customer who never got a reply.

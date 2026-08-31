# Cloudflare — tokens, Pages project, custom domain

## The two tokens

Two separate tokens, for two separate jobs. Do not make one token that does both — a
token that can edit DNS should not be sitting in a GitHub repository.

| Token | Lives | Permissions |
|---|---|---|
| **Deploy token** | GitHub repo secret `CLOUDFLARE_API_TOKEN` | Account → Cloudflare Pages → Edit |
| **DNS token** | Your shell only, for Phase 6 | Zone → DNS → Edit, Zone → Zone → Read, restricted to the one domain |

### Walking them through creating one

They have to do this in the browser; you cannot. Give the click path, not a description:

> 1. Go to **dash.cloudflare.com/profile/api-tokens**
> 2. **Create Token** → scroll to the bottom → **Create Custom Token** → **Get started**
> 3. Name it `<something recognisable>` — e.g. `example.com deploy`
> 4. Under **Permissions**, set the dropdowns to: `Account` · `Cloudflare Pages` · `Edit`
> 5. Under **Account Resources**, pick your account
> 6. **Continue to summary** → **Create Token**
> 7. Copy the token — **this is the only time it's shown**

For the DNS token, step 4 is two rows — `Zone` · `DNS` · `Edit` and `Zone` · `Zone` ·
`Read` — and under **Zone Resources** they pick `Include` · `Specific zone` · the one
domain.

Handling the value:

- The **deploy token** goes straight into the repo without passing through your hands:
  ```bash
  gh secret set CLOUDFLARE_API_TOKEN --repo <owner>/<repo>
  ```
  It prompts, and the value is not echoed. Ask them to run it, or paste into the prompt.
- The **DNS token** goes in their shell: `export CLOUDFLARE_API_TOKEN=...`
- Never write either into a file in the repo, never print one, never put one in a
  command line that lands in shell history.
- Tell them at handover that the DNS token can be deleted once setup is finished.

Find the account id (needed in the deploy file, and not secret):

```bash
npx wrangler whoami
```

## Create the Pages project

```bash
npx wrangler pages project create <project-name> --production-branch main
```

The project name becomes the free address `<project-name>.pages.dev`, so it must be
globally unique across all of Cloudflare. Derive it from the domain — `example.com` →
`example` — and if it is taken, try `example-web`, then the company name. Tell them
what it ended up as; it appears in every preview link they will ever click.

Check what exists first, so a re-run doesn't fail confusingly:

```bash
npx wrangler pages project list
```

**Do not connect the Pages project to GitHub in the Cloudflare dashboard.** Cloudflare's
own Git integration would build the site too, which means two systems deploying the same
repo and a preview link you cannot control the wording of. The whole point of the GitHub
Actions workflow is that it posts the preview comment itself. Leave the Pages project
with no Git connection; it receives finished builds by upload.

## First deploy

Once `web/` builds, do one deploy by hand to prove the pipeline before wiring CI:

```bash
cd web && npm ci && npm run build
npx wrangler pages deploy dist --project-name=<project-name> --branch=main
```

Open the `.pages.dev` address it prints and confirm the site is there.

This is the **only** manual deploy. After the workflow exists, deploying by hand puts
the live site out of step with the repo, which is exactly the confusion the whole
system is meant to prevent. `AGENTS.md` says so; follow your own rule.

## Prove the preview loop works

Before touching DNS, verify the mechanism end to end. This is the single most important
check in the skill — everything else is downstream of it.

```bash
git checkout -b test-preview
# make a small visible change, e.g. a word on the home page
git commit -am "Test the preview mechanism" && git push -u origin test-preview
gh pr create --title "Test the preview mechanism" --body "Checking the preview link appears."
```

Then watch for the comment:

```bash
gh run watch                     # the build
gh pr view --comments            # the preview link
```

Expect, within about two minutes, a comment containing a `.pages.dev` link. Open it and
confirm the change is visible there and **not** on the live site.

If it does not appear, check in this order:

| Symptom | Cause |
|---|---|
| Workflow didn't run at all | The file isn't at `.github/workflows/deploy.yml`, or the push lacked `workflow` scope |
| "Authentication error" from wrangler | Deploy token missing, wrong permissions, or the secret is misnamed |
| Build fails | `npm run build` doesn't pass in `web/` — fix locally first |
| Deploy works, no comment | The comment step needs `pull-requests: write` under `permissions:` |
| Comment appears with an empty link | Both output variables were empty — check the wrangler-action version is `@v3` |

Merge the test PR, confirm the live `.pages.dev` updates, then delete the branch.

### Check the preview address is reachable from where they sit

Do this early, because the entire system rests on people being able to open preview
links, and some corporate networks block `pages.dev` wholesale.

```bash
curl -s -o /dev/null -w '%{http_code}\n' -m 20 https://<project>.pages.dev/
```

`000` means it did not connect. Before assuming a deploy problem, work out which layer
is blocking:

```bash
dig +short A <project>.pages.dev              # resolving is fine? then it isn't DNS
curl -s -o /dev/null -w '%{http_code}\n' --resolve <live-domain>:443:<that-ip> https://<live-domain>/
```

If the name resolves and the *same IP* serves a custom domain happily while the
`pages.dev` name does not, the network is filtering on the hostname — usually the TLS
SNI. Two consequences worth stating plainly rather than discovering later:

- **Changing DNS to 8.8.8.8 does not fix this**, despite being the usual advice. The
  lookup was never the problem. Only allowing `*.pages.dev` through the network does,
  or using a connection that isn't filtered.
- **Test from a phone on mobile data** to confirm the site itself is fine before
  anyone starts debugging the deployment.

Raise it with them immediately if you find it. A team that cannot open preview links
cannot use the workflow at all, and it is far better framed as "your network blocks
this, here is what to ask IT for" than discovered in the middle of their first change.

## Environment variables and secrets

Anything the contact form needs is set on the **Pages project**, not in the repo:

```bash
npx wrangler pages secret put BREVO_API_KEY --project-name=<project-name>
```

Plain (non-secret) values like `CONTACT_TO` are set in the dashboard under the project's
**Settings → Variables and secrets**.

Two things that cause "it worked locally" confusion:

- **Pages binds variables at deploy time.** After adding or changing a secret, redeploy
  or the running site will not see it. Merging any small change is enough.
- **Secrets set on production are not visible to preview deployments.** That is
  deliberate — it means a preview cannot send real email. The contact form failing on a
  preview link is *expected behaviour*, not a bug. Say this at handover, or it will be
  reported as broken.

## Attach the custom domain

There is no `wrangler pages domain` command. Use the API, with the deploy token:

```bash
ACC=$(npx wrangler whoami 2>/dev/null | grep -oE '[0-9a-f]{32}' | head -1)

curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/$ACC/pages/projects/<project>/domains" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  -H 'content-type: application/json' \
  --data '{"name":"example.com"}' | jq '{success, errors}'

# list what's attached
curl -s "https://api.cloudflare.com/client/v4/accounts/$ACC/pages/projects/<project>/domains" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" | jq -r '.result[].name'
```

Attach both `example.com` and `www.example.com` unless they said otherwise.

Both, genuinely. Pages matches on the hostname it is asked for, so a name that is not
attached returns a **Pages 404** even when DNS points at it perfectly. The symptom —
"the main address works but `www` shows a Cloudflare not-found page" — looks like a DNS
fault and is not one. Attaching the missing name fixes it.

If the Pages project is in a different Cloudflare account from the domain, attachment
needs a verification step and whoever owns that account has to act. Establish early
whether the project and the domain are in the same account; if a developer built the
site in their own, that is a hand-over conversation, not something you can resolve.

When the domain's DNS is in the same Cloudflare account, attaching it creates the
needed DNS record automatically. **Check what it created** and report it — it is still a
DNS change, and it still gets shown to the person even though you did not write it by
hand. If DNS is elsewhere, it will instead print a record to create manually; treat that
as a Phase 6 proposal like any other.

The HTTPS certificate is issued automatically and usually takes a few minutes. If it
takes much longer, check for a `CAA` record blocking it — see `references/dns.md`, and
note that Pages needs both `letsencrypt.org` and `pki.goog` allowed.

## Deployment aliases lag

Immediately after a deploy, the custom domain and the project's main `.pages.dev`
address can briefly serve the *previous* build while the newest one is still being
attached. It resolves itself within about a minute.

Do not diagnose this as a configuration fault. If a just-deployed change isn't visible,
wait 60 seconds and check again before changing anything. Chasing this has cost real
time — the deployment-specific URL will already show the new build while the alias is
still catching up, which is how you tell the two apart.

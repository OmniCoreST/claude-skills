# DNS — audit and safe change

Read all of this before changing a single record. Every rule here comes from a mistake
that was actually made, and most of them fail *quietly*: nothing breaks while you are
watching, and something breaks days later.

DNS is the setting that tells the internet where a domain's website **and its email**
live. Both are in the same list of records. That is the whole problem — you are working
inches away from a live mail system the entire time.

## First: wrangler cannot do this

`wrangler` signs in with read-only access to zone settings. Writing a DNS record
returns a permissions error. There is no `wrangler dns` command, and no
`wrangler pages domain` command either. Both DNS records and custom-domain attachment
go through the Cloudflare REST API.

Do not go looking for a wrangler subcommand. Get a scoped token instead
(`references/cloudflare.md` has the click path):

- **Zone → DNS → Edit**
- **Zone → Zone → Read**
- **Zone Resources: restricted to this one domain**

One domain, not "all zones". A token that can only touch the domain you are working on
cannot damage a domain you are not.

## Step 1 — Find out where DNS actually lives

Three different things get confused constantly, and they are often three different
companies:

- **The registrar** — who you buy and renew the domain from.
- **The DNS host** — who answers questions about where the site and mail are. This is
  what you are editing.
- **The web host** — where the pages are served from.

Find the DNS host:

```bash
dig +short NS example.com
```

`*.ns.cloudflare.com` means Cloudflare is already the DNS host and you can proceed.
Anything else means DNS is elsewhere and you are in the "guide the move" path below.

If two providers appear, stop. Mixed delegation means some visitors get answers from
one and some from the other, and any edit you make is only seen by half the internet.
Resolve that before anything else.

## Step 2 — Audit before touching

Run `scripts/dns-audit.sh <domain>`. It reads the zone and sorts every record into four
buckets. It never writes.

| Bucket | What's in it | Rule |
|---|---|---|
| **Mail** | `MX`, `TXT` starting `v=spf1`, anything under `_domainkey`, `_dmarc` | Never touch |
| **Verification** | `TXT` like `google-site-verification=`, `MS=`, `brevo-code`, `_acme-challenge` | Never touch |
| **Website** | apex `A`/`AAAA`/`CNAME`, `www`, other site hostnames | This is your work |
| **Other** | `SRV`, `CAA`, service subdomains, anything unrecognised | Leave alone; ask if relevant |

Report the result in plain language before proposing anything:

> This domain has live email running through Google Workspace, plus two records proving
> ownership to Google and to your mail service. I'm not going to touch any of those.
> The website records are what I'll be changing: right now `example.com` and
> `www.example.com` both point at a server at 203.0.113.10.

**Deleting a verification record silently un-verifies the domain with that provider.**
Nothing breaks immediately. It surfaces weeks later when a certificate fails to renew or
a service quietly stops working. If you cannot identify what a `TXT` record is for,
that is a reason to leave it, not a reason to remove it.

### Records that follow the apex

Before changing the apex, list everything that points *at* it:

```bash
jq -r --arg d "$DOMAIN" '.result[] | select(.type=="CNAME" and (.content==$d)) | .name' <<<"$REC"
```

A `CNAME` whose target is the domain itself is not independent — it resolves to whatever
the apex resolves to. Repoint the apex at the new site and every one of them moves too,
silently, without appearing anywhere in your list of changes.

On shared hosting this is routine: `cpanel`, `whm`, `webdisk`, `webmail`, `ftp` and
often `mail` are all CNAMEs to the apex. Move the apex to Pages and the hosting control
panel, the file manager and the webmail login all stop reaching the server — which is
still running, still serving other subdomains, and now unreachable by the people who
administer it. Nothing errors. They simply get the new website instead of a login page.

So when the apex is changing and anything points at it, convert those to explicit `A`
records at the old server's address **first**, as a separate approved change, before
touching the apex. Then they stay where they are by their own definition rather than by
inheritance.

The same applies to any subdomain still served by the old host — a shop, a booking
system, a customer portal. Confirm what each one is before assuming the old server can
be switched off.

## Step 3 — Never guess the list of names

**DNS cannot be enumerated by asking it questions.** There is no "list all records"
query from outside. A name you did not think to ask about is invisible, not absent.

This is not theoretical. In the project this skill generalises from, a zone was copied
by probing for the names someone thought of. Four subdomains were not thought of. They
went dark at cutover and the cause took a day to find.

When you need the complete list — any migration, any comparison, any cleanup — build it
from sources that do not depend on guessing, and reconcile them:

1. **The provider's own control panel or API.** The only authoritative list. If you have
   access, this alone is enough.
2. **Certificate transparency logs** — `https://crt.sh/?q=%25.example.com&output=json`.
   Every certificate ever issued names the hostnames it covers. Finds things nobody
   remembers.
3. **A brute-force sweep** of ~150 common names (`www admin mail webmail ftp cpanel
   whm webdisk shop blog app api dev staging test portal vpn m …`), plus two-level
   probes for anything you find.
4. **The old site's own HTML** — links and image sources point at hostnames.

If the numbers from these sources disagree, you do not yet have the list. Say so and
find the difference before proceeding.

Watch for names that never appear in probing but exist in the panel — `cpanel`, `whm`,
`webdisk` are the usual ones on shared hosting.

## Step 4 — Propose each change individually

One record at a time. Current value, new value, plain consequence, then wait.

```
Change 1 of 2 — the main address

  example.com
    now:  points to a server at 203.0.113.10
    new:  points to your new site on Cloudflare
    effect: visitors start seeing the new site. Up to a few minutes for
            everyone to switch over. Reversible in one step.

  Not touching: your email settings, or the two ownership records.

  Shall I make this change?
```

Then apply it, confirm it, and move to the next. Do not batch. An approval for the main
address is not an approval for the `www` one, even though you will ask about that
immediately afterwards.

**Change `www` first, check it, then the main address.** `www` carries a fraction of the
traffic, so if something is wrong with the new site or the certificate you find out on
the quiet address rather than the one on the company's letterhead.

**Delete by record id, never by name.** Several records usually share the domain's root
name — the `MX`, the `SPF`, each verification `TXT`, any `CAA`. "Delete the A record at
example.com" is unambiguous to you and catastrophic if implemented as "delete everything
named example.com". Identify the exact record, delete that id, and say in the plan which
records share the name and are staying.

**Write down the old value before you overwrite it.** Put it in `SETUP-NOTES.md`, in
full, with the record type and TTL. Rollback then means restoring a value you have
written down rather than reconstructing one from memory while a site is down.

**Lower the TTL first if the change carries any risk.** The TTL is how long the rest of
the internet is allowed to remember the old answer. Drop it to 300 seconds, wait for the
*previous* TTL to elapse so the short one is what everyone now holds, then make the real
change. Rollback goes from "up to an hour" to "about five minutes". On a low-traffic
brochure site this is optional; on anything with a shop, a booking system or a login,
do it.

## Step 5 — Verify from outside

Your own computer's answer is worthless — it may be a local cache. Ask several public
resolvers, and check they agree:

```bash
for r in 1.1.1.1 8.8.8.8 9.9.9.9 208.67.222.222; do
  printf '%-16s ' "$r"; dig +short @"$r" example.com A
done
```

Consistency across resolvers matters more than any single answer — it is how you know a
change has actually reached everyone rather than just the resolver you happened to ask.

Then check the site actually loads over HTTPS, and that the certificate covers both the
bare and `www` forms.

---

# When DNS is not on Cloudflare yet

The domain has to be moved before you can manage it. This is the riskiest thing in the
whole skill, because the switch redirects **email lookups** as well as web lookups. Do
it in this order and it is safe. Skip a step and it is not.

Explain the plan first, in these terms:

> Your domain's settings live at [provider] today. To manage them here we move them to
> Cloudflare. Done in the right order this is invisible — no downtime, and your email
> keeps working throughout. The move takes about two days, almost all of it waiting.
> Nothing is irreversible until the very last step.

### 1. Copy everything first, changing nothing

Add the domain to Cloudflare. It imports what it can find automatically — treat that as
a starting point, not the answer, because import uses the same guessing that misses
records. Compare against the real list from Step 3 and add whatever is missing.

**Copy the records you intend to delete later, too.** The point of this phase is that
both providers give *identical* answers, so it does not matter which one a visitor's
computer happens to ask. That property is the entire reason the move is safe. Clean up
afterwards, never during.

**Set every record to "DNS only", not proxied.** The orange-cloud proxy makes Cloudflare
answer with its own addresses, which immediately breaks the identical-answers property.
Turn it on later as a separate change, once DNS is settled — two changes at once means
you cannot tell which one broke something.

### 2. Prove the two copies match

Ask both providers directly and compare, record by record:

```bash
dig +short @old-ns.example.net example.com MX
dig +short @<assigned>.ns.cloudflare.com example.com MX
```

Sort and normalise before comparing so ordering and spacing don't manufacture false
alarms. Every record must match, especially `MX` and everything mail-related. Do not
proceed on "close enough".

### 3. Hand over the nameservers

The person does this at their registrar — you cannot, and should not try.

> Cloudflare has given you two addresses. Log in where you bought the domain, find
> "Nameservers", and replace what's there with these two:
>
>     ana.ns.cloudflare.com
>     bob.ns.cloudflare.com
>
> Remove the old ones entirely — leaving both sets is worse than either alone. Tell me
> when it's saved and I'll watch for it to take effect.

### 4. Wait, and verify

Typically a few hours; it can be up to 48. The waiting period is not superstition —
the old settings are cached across the internet with a lifetime set by the registry,
which cannot be shortened after the fact.

Poll until every public resolver agrees on Cloudflare's nameservers. **The verified
agreement is the signal to continue, not the clock.**

### 5. Only now, clean up

Once the old nameservers have stopped answering, there is no second copy that could
keep serving a record you delete. Before that point, deleting anything is unsafe and
the change may appear not to work at all.

---

# Records with delayed failure modes

These three do not break when you get them wrong. They break later.

## CAA — the trap

A `CAA` record lists which certificate authorities may issue certificates for the
domain. Get it wrong and **nothing happens** — the current certificate keeps working
until it expires. Then renewal fails and the site goes down with a security warning,
months after the change that caused it, with no obvious connection.

Before writing any `CAA`, check who actually issued the certificate being served today:

```bash
echo | openssl s_client -connect example.com:443 -servername example.com 2>/dev/null \
  | openssl x509 -noout -issuer -dates
```

Then include **both** the current issuer and the issuer of anywhere you plan to move.
Cloudflare Pages issues from Let's Encrypt *and* Google Trust Services, so a record
naming only `letsencrypt.org` will eventually block renewal on Pages.

| Situation | Needs |
|---|---|
| Staying on Cloudflare Pages | `letsencrypt.org` + `pki.goog` |
| Staying on GoDaddy / cPanel | `godaddy.com` + `starfieldtech.com` |
| Moving to Pages from elsewhere | Both the old issuer and the two above, until the move is done |

**If you cannot enumerate every CA that will ever need to issue for this domain, write
no CAA record at all.** Absence means "anyone may issue", which is the default, is
always safe, and is what the domain has had all along. A missing CAA record has never
taken a site down; a wrong one regularly has.

## SPF — the ten-lookup budget

An `SPF` record lists who may send email as this domain. It may contain at most **ten**
mechanisms that require a DNS lookup (`include:`, `a:`, `mx:`, `ptr`, `exists:`,
`redirect=`). Exceed it and the record stops being evaluated — every message becomes
unauthenticated, everywhere, at once.

Count before adding anything:

```bash
dig +short TXT example.com | grep v=spf1 | grep -o -E 'include:|a:|mx:|ptr|exists:|redirect=' | wc -l
```

Adding a contact form does **not** require an SPF change. The form sends through Brevo
using Brevo's own domain, not the site's. Only change SPF if mail is genuinely being
sent *as* this domain from somewhere new — and then only after confirming what is
already listed.

`-all` (reject anything not listed) versus `~all` (flag it) is a decision about who
else sends mail for this domain, and you usually cannot know that. **Never tighten
`~all` to `-all` speculatively.** If an old web host runs a PHP contact form nobody
remembers, `-all` starts silently rejecting it.

## DMARC — change policy on evidence, not on schedule

`_dmarc` tells receivers what to do with mail that fails authentication. `p=none` is
monitoring only.

Safe to add: `fo=1`, which asks receivers for failure reports. It changes no policy and
cannot affect delivery. Adding a second reporting address is likewise inert.

Not safe to change casually: `p=none` → `p=quarantine` → `p=reject`. That ladder is
climbed after roughly 30 days of clean reports at each step, on evidence. Never jump it
because the site launched.

---

# Cloudflare API cookbook

Token in the environment, never in a file, never printed:

```bash
export CLOUDFLARE_API_TOKEN=...     # never commit, never echo
API=https://api.cloudflare.com/client/v4
AUTH="Authorization: Bearer $CLOUDFLARE_API_TOKEN"
```

```bash
# Zone id
ZID=$(curl -s "$API/zones?name=example.com" -H "$AUTH" | jq -r '.result[0].id')

# Every record (one call, then work from the snapshot)
REC=$(curl -s "$API/zones/$ZID/dns_records?per_page=500" -H "$AUTH")

# Always check success — a failed call returns nulls that look like data
jq -e '.success' <<<"$REC" >/dev/null || { echo "read failed"; exit 1; }

# Create / update / delete
curl -s -X POST "$API/zones/$ZID/dns_records" -H "$AUTH" \
  -H 'content-type: application/json' \
  --data '{"type":"CNAME","name":"www.example.com","content":"example.pages.dev","ttl":300,"proxied":false}'

curl -s -X PATCH  "$API/zones/$ZID/dns_records/$ID" -H "$AUTH" ...
curl -s -X DELETE "$API/zones/$ZID/dns_records/$ID" -H "$AUTH"
```

**Always test `.success`.** A token without the right permissions returns a
well-formed response whose fields are `null`. Read that as data and you will conclude
the zone is empty, or that a setting is unset, when in fact you were never allowed to
look. Check `.success` and `.errors[].message` on every call.

**`PATCH` is sometimes rejected** with "Method not allowed for this authentication
scheme" on tokens where `POST` and `DELETE` both work. Fall back to delete-then-create,
but only for records where a few seconds of absence is harmless. That is fine for a
`p=none` DMARC record. It is **not** fine for `MX` or a DKIM key — a gap there loses
mail, so if `PATCH` fails on those, stop and hand it to a person.

## Writing scripts

If you write a DNS script, follow these — each is a bug already paid for:

```bash
set -uo pipefail        # NOT -e: a failed delete must not abort mid-cleanup,
                        # leaving the zone half-changed. Count failures, report
                        # them at the end, exit non-zero then.

COUNT=$((COUNT + 1))    # never ((COUNT++)) as a function's last command:
                        # it evaluates to the value BEFORE incrementing, so it
                        # returns non-zero when the counter is 0 and silently
                        # poisons the exit status.
```

- `dig +short A name` on an alias also returns the alias target. Query `CNAME` first and
  only fall back to `A` when the name is genuinely not an alias, or you will
  double-report it.
- In standard DNS a `CNAME` cannot coexist with any other record at the same name, so
  when copying a zone, create it first and skip the other types for that name.

  **Cloudflare is the exception, and it matters.** Cloudflare flattens a `CNAME` at the
  domain's root, so `example.com → example.pages.dev` sits happily alongside the `MX`,
  `SPF` and verification records at that same name. This is the normal, supported way to
  point a root domain at Pages. Do not read the standard rule as a reason to delete `MX`
  to "make room" — that would take the company's email down to solve a problem that does
  not exist here.
- `TXT` records over 255 bytes arrive as several quoted chunks on one line. Rejoin them
  into a single value before sending; Cloudflare re-splits on the way out.
  `sed 's/" "//g; s/^"//; s/"$//'`
- `curl` prints `000` and exits non-zero on a TLS failure. Swallow the status so the
  `000` isn't concatenated with a fallback: `code=$(curl ... -w '%{http_code}'; true)`
- Make every script idempotent — check whether the record already has the wanted value
  and skip it. Re-running after a partial failure must not duplicate records.
- Give every mutating script `--dry-run`, and short-circuit inside the single helper
  that performs each verb, so there is exactly one place per verb where a write happens.

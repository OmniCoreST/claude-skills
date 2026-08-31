#!/usr/bin/env bash
# Read a Cloudflare zone and sort every record by how dangerous it is to touch.
#
#   export CLOUDFLARE_API_TOKEN=...      # Zone:Read + Zone:DNS:Read is enough
#   ./dns-audit.sh example.com
#
# READ-ONLY. It issues one GET and never writes, so it cannot break anything.
# Run it before proposing any change, and show the person the output.

set -uo pipefail

DOMAIN="${1:-}"
[[ -z "$DOMAIN" ]] && { echo "usage: $0 <domain>"; exit 2; }
: "${CLOUDFLARE_API_TOKEN:?set CLOUDFLARE_API_TOKEN first (see references/cloudflare.md)}"

API="https://api.cloudflare.com/client/v4"
AUTH="Authorization: Bearer $CLOUDFLARE_API_TOKEN"

bold() { printf '\033[1m%s\033[0m\n' "$1"; }
red()  { printf '\033[31m%s\033[0m' "$1"; }
grn()  { printf '\033[32m%s\033[0m' "$1"; }
yel()  { printf '\033[33m%s\033[0m' "$1"; }

ZONES=$(curl -s "$API/zones?name=$DOMAIN" -H "$AUTH")
# A token without the right permissions returns a well-formed body whose fields
# are null. Reading that as data looks like "the zone is empty" — always test
# .success before trusting anything in the response.
jq -e '.success' <<<"$ZONES" >/dev/null || {
  echo "Could not read zones: $(jq -rc '[.errors[]?.message]|join("; ")' <<<"$ZONES")"
  exit 1
}

ZID=$(jq -r '.result[0].id // empty' <<<"$ZONES")
if [[ -z "$ZID" ]]; then
  # An empty result means one of two very different things, and saying the wrong
  # one sends people hunting for a problem that does not exist. A token scoped to
  # specific zones returns success with an empty list for every zone outside its
  # scope — identical on the wire to a domain that genuinely is not here.
  VISIBLE=$(curl -s "$API/zones?per_page=50" -H "$AUTH" | jq -r '[.result[]?.name] | join(", ")')
  echo
  echo "Could not read $DOMAIN with this token."
  if [[ -n "$VISIBLE" ]]; then
    echo "  The token is scoped to: $VISIBLE"
    echo "  That is why $DOMAIN comes back empty — not proof the domain is absent."
    echo "  Either use a token that includes $DOMAIN, or add it under Zone Resources."
  else
    echo "  This token can see no zones at all — check its Zone:Read permission."
  fi
  echo
  echo "  To find out where the domain's DNS really lives:  dig +short NS $DOMAIN"
  echo "  Cloudflare nameservers (*.ns.cloudflare.com) mean the zone exists in SOME"
  echo "  account — possibly this one, just outside the token's scope."
  exit 1
fi

REC=$(curl -s "$API/zones/$ZID/dns_records?per_page=500" -H "$AUTH")
jq -e '.success' <<<"$REC" >/dev/null || {
  echo "Could not read records: $(jq -rc '[.errors[]?.message]|join("; ")' <<<"$REC")"
  exit 1
}

TOTAL=$(jq '.result | length' <<<"$REC")
printf '\n'
bold "$DOMAIN — $TOTAL records (zone $ZID)"

# jq filter deciding which bucket a record belongs to. Kept in one place so the
# classification can't drift between the sections below.
#
# The two mail-provider tests exist because of a real misclassification: a mail
# service's branded sending records (em./r./img.em. pointing at brevosend.com)
# are ordinary CNAMEs and look exactly like website records. Deleting one breaks
# tracked links and images in every email the company sends — and the damage is
# invisible from the website. Judge these by where they POINT, not by their type.
CLASSIFY='
  def mailhost: "(?i)(brevosend|brevo\\.com|dkim|sendgrid\\.net|mailgun|mandrillapp|amazonses|mcsv\\.net|mcdlv\\.net|postmarkapp|sparkpostmail|mailer|pphosted|protection\\.outlook|mail\\.microsoft)";
  def mailname: "(?i)^(em|mail|smtp|mta|bounce|bounces|track|click|link|news|mailer)\\.";
  def servicehost: "(?i)(lync\\.com|online\\.lync|manage\\.microsoft|enterpriseregistration|windows\\.net|sharepoint\\.com|outlook\\.com|officeapps|zoom\\.us|atlassian\\.net|okta\\.com|duosecurity)";
  def servicename: "(?i)^(autodiscover|sip|lyncdiscover|enterpriseregistration|enterpriseenrollment|msoid|cpanel|whm|webdisk|webmail|cpcalendars|cpcontacts|ftp|vpn|remote|ns[0-9])\\.";
  def bucket:
    if   .type == "MX"                                             then "mail"
    elif .type == "TXT" and (.content | test("^\"?v=spf1"))        then "mail"
    elif .name | test("_domainkey")                                then "mail"
    elif .name | test("^_dmarc\\.")                                then "mail"
    elif .type == "CNAME" and (.content | test(mailhost))          then "mail"
    elif (.type == "CNAME" or .type == "A") and (.name | test(mailname)) then "mail"
    elif .type == "TXT" and (.content | test("(?i)verification|^\"?MS=|brevo-code|_acme-challenge|site-verification")) then "verify"
    elif .type == "TXT" and (.name | test("^_"))                   then "verify"
    # Service endpoints — device management, chat, control panels. They are
    # ordinary A/CNAME records and look like website records, but nothing here
    # serves the website. Deleting one breaks a system nobody is looking at.
    elif (.type == "CNAME" or .type == "A") and (.content | test(servicehost)) then "other"
    elif (.type == "CNAME" or .type == "A") and (.name | test(servicename))    then "other"
    elif (.type == "A" or .type == "AAAA" or .type == "CNAME")     then "web"
    else "other" end;
'

# BSD column (macOS) collapses repeated delimiters, so a tab-aligned table can
# come out ragged there, and column is missing entirely in minimal images. Falling
# back to the raw tab-separated lines keeps the audit readable either way — this
# output is safety information, so it must never fail to print.
tidy_table() {
  if command -v column >/dev/null 2>&1; then
    column -t -s "$(printf '\t')" 2>/dev/null || sed 's/\t/  /g'
  else
    sed 's/\t/  /g'
  fi
}

show() { # bucket, heading, note
  local n
  n=$(jq --arg b "$1" "$CLASSIFY"' [.result[] | select(bucket == $b)] | length' <<<"$REC")
  printf '\n'
  bold "$2  ($n)"
  [[ -n "${3:-}" ]] && printf '  %s\n' "$3"
  (( n == 0 )) && { printf '  (none)\n'; return; }
  jq -r --arg b "$1" "$CLASSIFY"'
    .result[] | select(bucket == $b)
    | "  \(.type)\t\(.name)\t\(.content | if length > 68 then .[0:65] + "..." else . end)\(if .proxied then "\t[proxied]" else "" end)"
  ' <<<"$REC" | tidy_table
}

show mail   "$(red 'MAIL — never touch')" \
  "Changing any of these can stop the company receiving or sending email."
show verify "$(red 'VERIFICATION — never touch')" \
  "These prove domain ownership to other services. Deleting one un-verifies it silently."
show web    "$(grn 'WEBSITE — this is what you may change')" \
  "Where the site is served from. Safe to change, one at a time, with approval."
show other  "$(yel 'OTHER — leave alone unless asked')" \
  "Ask before touching anything here. If you cannot identify it, that is a reason to leave it."

printf '\n'
bold 'Checks'

# --- SPF lookup budget --------------------------------------------------------
# SPF allows at most 10 mechanisms that require a DNS lookup. Past that the whole
# record stops being evaluated and every message becomes unauthenticated at once.
spf=$(jq -r '.result[] | select(.type=="TXT") | .content | select(test("v=spf1"))' <<<"$REC" | head -1)
if [[ -n "$spf" ]]; then
  lookups=$(grep -o -E 'include:|a:|mx:|ptr|exists:|redirect=' <<<"$spf" | wc -l)
  if (( lookups <= 10 )); then
    printf '  %s SPF uses %d of its 10 allowed lookups\n' "$(grn '✓')" "$lookups"
  else
    printf '  %s SPF uses %d lookups — over the limit of 10, so it is being ignored entirely\n' "$(red '✗')" "$lookups"
  fi
  case "$spf" in
    *-all*) printf '  %s SPF ends in -all (hard fail): anything not listed is rejected outright\n' "$(yel '!')" ;;
    *~all*) printf '  %s SPF ends in ~all (soft fail)\n' "$(grn '✓')" ;;
  esac
else
  printf '  %s No SPF record\n' "$(yel '!')"
fi

# --- mail present? ------------------------------------------------------------
mx=$(jq -r '[.result[] | select(.type=="MX")] | length' <<<"$REC")
if (( mx > 0 )); then
  printf '  %s %d MX record(s) — this domain handles live email. Touch nothing mail-related.\n' "$(yel '!')" "$mx"
fi

# --- CAA ----------------------------------------------------------------------
# CAA never breaks the current certificate — it breaks the next renewal, months
# later, with no obvious connection to the change that caused it.
caa=$(jq -r '[.result[] | select(.type=="CAA")] | length' <<<"$REC")
if (( caa > 0 )); then
  printf '  %s %d CAA record(s) present. Cloudflare Pages needs BOTH letsencrypt.org and pki.goog;\n' "$(yel '!')" "$caa"
  printf '    a set missing either will block certificate renewal at some point in the future.\n'
  jq -r '.result[] | select(.type=="CAA") | "      \(.content)"' <<<"$REC"
else
  printf '  %s No CAA records — any certificate authority may issue. This is the safe default.\n' "$(grn '✓')"
fi

# --- proxied during a migration ----------------------------------------------
prox=$(jq -r '[.result[] | select(.proxied == true)] | length' <<<"$REC")
if (( prox > 0 )); then
  printf '  %s %d record(s) are proxied. During a nameserver migration this breaks the\n' "$(yel '!')" "$prox"
  printf '    "both providers answer identically" property the cutover depends on.\n'
fi

printf '\n  Read-only — nothing was changed.\n'
printf '  Show this to the person before proposing any change.\n\n'
exit 0

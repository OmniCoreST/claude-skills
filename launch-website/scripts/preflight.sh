#!/usr/bin/env bash
# Preflight for the launch-website skill.
#
#   ./preflight.sh
#
# Reports what is installed and what is signed in. Read-only — holds no
# credentials and changes nothing, so it is always safe to run first.

set -uo pipefail   # deliberately not -e: one missing tool must not stop the
                   # report. Collect every problem, print them all, exit once.

OK=0; WARN=0; FAIL=0
grn() { printf '\033[32m%s\033[0m' "$1"; }
red() { printf '\033[31m%s\033[0m' "$1"; }
yel() { printf '\033[33m%s\033[0m' "$1"; }

# Counters are plain assignments, never `((N++))` as a function's last command:
# that evaluates to the value BEFORE incrementing, so it returns non-zero when
# the counter is 0 and silently poisons the exit status.
ok()   { printf '  %s %s\n' "$(grn '✓')" "$1"; OK=$((OK + 1)); }
warn() { printf '  %s %s\n' "$(yel '!')" "$1"; WARN=$((WARN + 1)); }
bad()  { printf '  %s %s\n' "$(red '✗')" "$1"; FAIL=$((FAIL + 1)); }

printf '\n\033[1mTools\033[0m\n'

if command -v node >/dev/null 2>&1; then
  ver=$(node --version | tr -d 'v'); major=${ver%%.*}
  if (( major >= 20 )); then ok "node $ver"
  else bad "node $ver — need 20 or newer (the deploy workflow builds on 20)"; fi
else
  bad "node is not installed — https://nodejs.org (choose the LTS version)"
fi

for t in npm git curl jq; do
  if command -v "$t" >/dev/null 2>&1; then ok "$t"
  else bad "$t is not installed"; fi
done

if command -v dig >/dev/null 2>&1; then ok "dig"
else warn "dig is not installed — needed for DNS checks (package: bind-utils or dnsutils)"; fi

# wrangler is used via npx, so a global install is not required.
if command -v wrangler >/dev/null 2>&1; then ok "wrangler $(wrangler --version 2>/dev/null | tail -1)"
else ok "wrangler will be used via npx (no install needed)"; fi

printf '\n\033[1mGitHub\033[0m\n'

if ! command -v gh >/dev/null 2>&1; then
  bad "gh is not installed — https://cli.github.com"
elif gh auth status >/dev/null 2>&1; then
  who=$(gh api user --jq .login 2>/dev/null || echo '?')
  ok "signed in as $who"

  # The workflow scope is required to push .github/workflows/. Without it the
  # push is rejected with a message that does not name the missing scope.
  scopes=$(gh auth status 2>&1 | grep -i 'token scopes' | head -1)
  case "$scopes" in
    *workflow*) ok "token can create workflow files" ;;
    *) bad "token lacks the 'workflow' scope — pushing the deploy file will fail.
       Fix: gh auth refresh -h github.com -s workflow" ;;
  esac
  case "$scopes" in
    *repo*) ok "token can create and write repositories" ;;
    *) bad "token lacks the 'repo' scope.  Fix: gh auth refresh -h github.com -s repo" ;;
  esac

  orgs=$(gh api user/orgs --jq '.[].login' 2>/dev/null | tr '\n' ' ' | sed 's/ *$//; s/ /, /g')
  [[ -n "$orgs" ]] && ok "organisations available: $orgs"
else
  bad "not signed in to GitHub.  Fix: gh auth login"
fi

printf '\n\033[1mCloudflare\033[0m\n'

if npx --no-install wrangler whoami >/dev/null 2>&1 || npx -y wrangler whoami >/dev/null 2>&1; then
  acc=$(npx -y wrangler whoami 2>/dev/null | grep -oE '[0-9a-f]{32}' | head -1)
  if [[ -n "$acc" ]]; then ok "signed in — account id $acc"
  else warn "wrangler ran but no account id found; check 'npx wrangler whoami'"; fi
else
  warn "not signed in to Cloudflare.  Fix: npx wrangler login
       (a separate API token is still needed for the deploy — see references/cloudflare.md)"
fi

if [[ -n "${CLOUDFLARE_API_TOKEN:-}" ]]; then
  ok "CLOUDFLARE_API_TOKEN is set in this shell"   # never print the value
else
  warn "CLOUDFLARE_API_TOKEN not set — needed only for DNS work in Phase 6"
fi

printf '\n  %d ok   %d to check   %d blocking\n\n' "$OK" "$WARN" "$FAIL"

if (( FAIL > 0 )); then
  echo "  Fix the blocking items before starting. Everything else can wait."
  exit 1
fi
echo "  Ready."
exit 0

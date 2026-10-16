#!/usr/bin/env bash
# OWNER ONLY (prompt 03 §8): stores the Claude subscription token in OpenBao
# and restarts claude-runtime so it loads it.
#   1. in a separate terminal, as user Hub:   claude setup-token
#   2. then:                                  make claude-token   (paste; input is hidden)
# The token is never printed, never written to disk and never put in argv.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HQ="$REPO_DIR/infra/compose/hq.sh"
SECRETS_DIR="${HQ_SECRETS_DIR:-/home/Hub/.secrets}"
ADMIN_FILE="$SECRETS_DIR/openbao-admin.token"
BAO_ADDR="${HQ_BAO_ADDR:-http://127.0.0.1:8200}"

die() { printf 'claude-token: %s\n' "$*" >&2; exit 1; }

[[ -t 0 ]] || die "run this in an interactive terminal"
[[ -s "$ADMIN_FILE" ]] || die "no OpenBao admin token yet; run 'make up' first"

printf 'Paste the token printed by "claude setup-token" (input is hidden), then press Enter:\n> '
IFS= read -rs token
printf '\n'
token="${token//[[:space:]]/}"
[[ -n "$token" ]] || die "nothing was pasted"
# The browser login code ("code#state") is pasted into the setup-token window,
# not here; only the sk-ant-oat... line that window prints afterwards is the token.
[[ "$token" != *'#'* ]] || die "that is the login code from the browser, not the token: paste it into the 'claude setup-token' window, then paste the sk-ant-oat... line it prints here; nothing was saved"
[[ "$token" =~ ^[A-Za-z0-9_-]+$ ]] || die "a token has only letters, digits, '-' and '_'; nothing was saved"
[[ "$token" == sk-ant-oat* ]] || die "a subscription token starts with sk-ant-oat; nothing was saved"
((${#token} >= 40)) || die "that is too short to be a Claude token; nothing was saved"

umask 077
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
printf 'X-Vault-Token: %s\n' "$(cat "$ADMIN_FILE")" >"$work/auth"
code="$(TOK="$token" jq -n '{data: {token: env.TOK}}' |
  curl -sS -o /dev/null -w '%{http_code}' -H @"$work/auth" -H 'Content-Type: application/json' \
    --data-binary @- "$BAO_ADDR/v1/kv/data/claude-runtime/oauth")"
unset token
[[ "$code" == 200 || "$code" == 204 ]] || die "OpenBao refused the write (HTTP $code); nothing was saved"
printf 'Saved in OpenBao (kv/claude-runtime/oauth). Restarting claude-runtime...\n'

"$HQ" restart claude-runtime >/dev/null 2>&1
state=""
for _ in $(seq 1 45); do
  state="$("$HQ" exec -T claude-runtime cat /tmp/hq-health.json 2>/dev/null | jq -r '.oauth // empty' 2>/dev/null || true)"
  [[ "$state" == configured ]] && break
  sleep 2
done
[[ "$state" == configured ]] || die "claude-runtime did not report the token as loaded"
printf 'claude-runtime: token loaded. Done - tell Claude on the server that the token is set.\n'

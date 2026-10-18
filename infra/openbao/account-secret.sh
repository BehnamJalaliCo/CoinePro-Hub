#!/usr/bin/env bash
# OWNER ONLY (prompt 07 §2.5): stores the secret of one holding service account
# (an API key, a token, a session cookie or a password) in OpenBao, at
# kv/tools/accounts/<KEY>. The account's metadata and injection policy are
# added in the app (POST /api/v1/tools/accounts); the secret never goes
# through the API, a model or a log.
#   make account-secret KEY=<key>      (paste; input is hidden)
# The secret is never printed, never written to disk and never put in argv.
set -euo pipefail

SECRETS_DIR="${HQ_SECRETS_DIR:-/home/Hub/.secrets}"
ADMIN_FILE="$SECRETS_DIR/openbao-admin.token"
BAO_ADDR="${HQ_BAO_ADDR:-http://127.0.0.1:8200}"
KEY="${1:-${KEY:-}}"

die() { printf 'account-secret: %s\n' "$*" >&2; exit 1; }

[[ -t 0 ]] || die "run this in an interactive terminal (your own SSH session)"
[[ "$KEY" =~ ^[a-z0-9][a-z0-9_.-]{1,40}$ ]] || die "KEY=<key> as in the app (a-z, 0-9, . _ -)"
[[ -s "$ADMIN_FILE" ]] || die "no OpenBao admin token yet; run 'make up' first"

printf 'Paste the secret of service account "%s" (input is hidden), then press Enter:\n> ' "$KEY"
IFS= read -rs secret
printf '\n'
[[ -n "$secret" ]] || die "nothing was pasted; nothing was saved"
((${#secret} <= 8000)) || die "longer than 8000 characters; nothing was saved"

umask 077
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
printf 'X-Vault-Token: %s\n' "$(cat "$ADMIN_FILE")" >"$work/auth"
code="$(SEC="$secret" jq -n '{data: {secret: env.SEC}}' |
  curl -sS -o /dev/null -w '%{http_code}' -H @"$work/auth" -H 'Content-Type: application/json' \
    --data-binary @- "$BAO_ADDR/v1/kv/data/tools/accounts/$KEY")"
unset secret
[[ "$code" == 200 || "$code" == 204 ]] || die "OpenBao refused the write (HTTP $code); nothing was saved"
printf 'Saved in OpenBao (kv/tools/accounts/%s; the value is not shown).\n' "$KEY"
printf 'The account shows has_secret: true in the app; agents may use it from their next call.\n'

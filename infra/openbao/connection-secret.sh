#!/usr/bin/env bash
# OWNER ONLY (prompt 12 §9, contract §21.7): stores the API key of a new LLM
# connection in OpenBao, at kv/llm-connections/<KEY> (the connection's
# secret_ref). The connection itself is made in the app (POST /connections,
# sealed); it waits in `pending_secret` until its key is there, then
# llm-router verifies it at no token cost (its model list) -> ready or error.
#   make connection-secret KEY=<key>      (paste; input is hidden)
# The key is never printed, never written to disk and never put in argv; the
# server's Claude never runs this.
set -euo pipefail

SECRETS_DIR="${HQ_SECRETS_DIR:-/home/Hub/.secrets}"
ADMIN_FILE="$SECRETS_DIR/openbao-admin.token"
BAO_ADDR="${HQ_BAO_ADDR:-http://127.0.0.1:8200}"
KEY="${1:-${KEY:-}}"

die() { printf 'connection-secret: %s\n' "$*" >&2; exit 1; }

[[ -t 0 ]] || die "run this in an interactive terminal (your own SSH session)"
[[ "$KEY" =~ ^[a-z0-9][a-z0-9-]{1,62}$ ]] || die "KEY=<key> as in the app (a-z, 0-9, -)"
[[ -s "$ADMIN_FILE" ]] || die "no OpenBao admin token yet; run 'make up' first"

printf 'Paste the API key of connection "%s" (input is hidden), then press Enter:\n> ' "$KEY"
IFS= read -rs secret
printf '\n'
[[ -n "$secret" ]] || die "nothing was pasted; nothing was saved"
((${#secret} >= 8 && ${#secret} <= 8192)) || die "a key is 8 to 8192 characters; nothing was saved"

umask 077
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
printf 'X-Vault-Token: %s\n' "$(cat "$ADMIN_FILE")" >"$work/auth"
code="$(SEC="$secret" jq -n '{data: {api_key: env.SEC}}' |
  curl -sS -o /dev/null -w '%{http_code}' -H @"$work/auth" -H 'Content-Type: application/json' \
    --data-binary @- "$BAO_ADDR/v1/kv/data/llm-connections/$KEY")"
unset secret
[[ "$code" == 200 || "$code" == 204 ]] || die "OpenBao refused the write (HTTP $code); nothing was saved"
printf 'Saved in OpenBao (kv/llm-connections/%s; the value is not shown).\n' "$KEY"
printf 'llm-router verifies it within a minute (no token is spent); the app shows ready or error.\n'

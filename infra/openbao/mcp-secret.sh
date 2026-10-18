#!/usr/bin/env bash
# OWNER ONLY (prompt 07 §3): the secret of one MCP server (an API key or a
# token the server wants in its auth header) into OpenBao, at
# kv/hq-api/tools/mcp/<KEY>, where the api reads it for one call at a time.
#   make mcp-secret KEY=<server key>     (paste; input is hidden)
# The value is never printed, never written to disk and never put in argv;
# nobody reads it back through the API (GET /tools/mcp only says has_secret).
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SECRETS_DIR="${HQ_SECRETS_DIR:-/home/Hub/.secrets}"
ADMIN_FILE="$SECRETS_DIR/openbao-admin.token"
BAO_ADDR="${HQ_BAO_ADDR:-http://127.0.0.1:8200}"
KEY="${1:-}"

die() { printf 'mcp-secret: %s\n' "$*" >&2; exit 1; }

[[ "$KEY" =~ ^[a-z][a-z0-9-]{1,39}$ ]] || die "usage: make mcp-secret KEY=<server key, as registered>"
[[ -t 0 ]] || die "run this in an interactive terminal"
[[ -s "$ADMIN_FILE" ]] || die "no OpenBao admin token yet; run 'make up' first"
cd "$REPO_DIR"

printf 'Paste the secret of MCP server "%s" (input is hidden), then press Enter:\n> ' "$KEY"
IFS= read -rs secret
printf '\n'
secret="${secret//[[:space:]]/}"
[[ -n "$secret" ]] || die "nothing was pasted; nothing was saved"
((${#secret} <= 4096)) || die "that is longer than 4096 characters; nothing was saved"

umask 077
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
printf 'X-Vault-Token: %s\n' "$(cat "$ADMIN_FILE")" >"$work/auth"
code="$(SEC="$secret" jq -n '{data: {token: env.SEC}}' |
  curl -sS -o /dev/null -w '%{http_code}' -H @"$work/auth" -H 'Content-Type: application/json' \
    --data-binary @- "$BAO_ADDR/v1/kv/data/hq-api/tools/mcp/$KEY")"
unset secret
[[ "$code" == 200 || "$code" == 204 ]] || die "OpenBao refused the write (HTTP $code); nothing was saved"
printf 'Saved in OpenBao (kv/hq-api/tools/mcp/%s). The next call of that server uses it.\n' "$KEY"

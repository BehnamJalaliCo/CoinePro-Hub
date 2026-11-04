#!/usr/bin/env bash
# OWNER ONLY, in the owner's own terminal (prompt 22, contract §30.4): copy the HMAC secret that
# n8n and the hub share (N8N_SIGNING_PASSWORD in infra/compose/.env, made by `make env`) into
# OpenBao at kv/hq/n8n (key `secret`), where the api and the worker read it. The value is never
# printed, never put in argv and never written anywhere else.
#   make n8n-secret                  (written once; REPLACE=yes replaces it, then restart n8n)
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${HQ_ENV_FILE:-$REPO_DIR/infra/compose/.env}"
SECRETS_DIR="${HQ_SECRETS_DIR:-/home/Hub/.secrets}"
ADMIN_FILE="$SECRETS_DIR/openbao-admin.token"
BAO_ADDR="${HQ_BAO_ADDR:-http://127.0.0.1:8200}"
REPLACE="${REPLACE:-no}"

die() { printf 'n8n-secret: %s\n' "$*" >&2; exit 1; }

[[ -r "$ENV_FILE" ]] || die "no $ENV_FILE (run make env)"
[[ -s "$ADMIN_FILE" ]] || die "no OpenBao admin token yet; run 'make up' first"
secret="$(sed -n 's/^N8N_SIGNING_PASSWORD=//p' "$ENV_FILE" | tail -n1)"
((${#secret} >= 32)) || { unset secret; die "N8N_SIGNING_PASSWORD is not set in the env file (run make env)"; }

umask 077
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
printf 'X-Vault-Token: %s\n' "$(cat "$ADMIN_FILE")" >"$work/auth"
opts='{cas: 0}'
[[ "$REPLACE" == yes ]] && opts='{}'
code="$(SEC="$secret" jq -n "{options: $opts, data: {secret: env.SEC}}" |
  curl -sS -o "$work/resp" -w '%{http_code}' -H @"$work/auth" -H 'Content-Type: application/json' \
    --data-binary @- "$BAO_ADDR/v1/kv/data/hq/n8n")"
unset secret
if [[ "$code" == 400 ]] && grep -q 'check-and-set' "$work/resp"; then
  die "a secret exists already; nothing was changed (REPLACE=yes to replace it)"
fi
[[ "$code" == 200 || "$code" == 204 ]] || die "OpenBao refused the write (HTTP $code); nothing was saved"
printf 'Saved in OpenBao (kv/hq/n8n; the value is not shown).\n'

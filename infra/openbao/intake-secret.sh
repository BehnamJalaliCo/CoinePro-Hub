#!/usr/bin/env bash
# OWNER ONLY (prompt 10 §9): the HMAC secret of one intake source of one
# company, at kv/support/intake/<COMPANY>/<SOURCE> (SOURCE = chatwoot | product).
# The same secret goes into that source's own settings (Chatwoot's webhook, the
# product's CR-009/010 sender); the hub checks HMAC-SHA256 over "<timestamp>.<body>".
#   make intake-secret COMPANY=TY SOURCE=product      (paste; input is hidden)
# Make one in your own terminal first if the source does not give one
# (e.g. `openssl rand -hex 32`). Written with cas 0 the first time (an existing
# secret is replaced only with REPLACE=yes). Never printed, never written to
# disk, never put in argv.
set -euo pipefail

SECRETS_DIR="${HQ_SECRETS_DIR:-/home/Hub/.secrets}"
ADMIN_FILE="$SECRETS_DIR/openbao-admin.token"
BAO_ADDR="${HQ_BAO_ADDR:-http://127.0.0.1:8200}"
COMPANY="${1:-${COMPANY:-}}"
SOURCE="${2:-${SOURCE:-}}"
REPLACE="${REPLACE:-no}"

die() { printf 'intake-secret: %s\n' "$*" >&2; exit 1; }

[[ -t 0 ]] || die "run this in an interactive terminal (your own SSH session)"
[[ "$COMPANY" =~ ^[A-Z][A-Z0-9]{1,9}$ ]] || die "COMPANY=<company code> (e.g. TY)"
[[ "$SOURCE" == chatwoot || "$SOURCE" == product ]] || die "SOURCE=chatwoot or SOURCE=product"
[[ -s "$ADMIN_FILE" ]] || die "no OpenBao admin token yet; run 'make up' first"

printf 'Paste the %s intake secret of %s (input is hidden), then press Enter:\n> ' "$SOURCE" "$COMPANY"
IFS= read -rs secret
printf '\n'
((${#secret} >= 32 && ${#secret} <= 512)) || { unset secret; die "32 to 512 characters; nothing was saved"; }

umask 077
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
printf 'X-Vault-Token: %s\n' "$(cat "$ADMIN_FILE")" >"$work/auth"
opts='{cas: 0}'
[[ "$REPLACE" == yes ]] && opts='{}'
code="$(SEC="$secret" jq -n "{options: $opts, data: {secret: env.SEC}}" |
  curl -sS -o "$work/resp" -w '%{http_code}' -H @"$work/auth" -H 'Content-Type: application/json' \
    --data-binary @- "$BAO_ADDR/v1/kv/data/support/intake/$COMPANY/$SOURCE")"
unset secret
if [[ "$code" == 400 ]] && grep -q 'check-and-set' "$work/resp"; then
  die "a secret exists already; nothing was changed (REPLACE=yes to replace it)"
fi
[[ "$code" == 200 || "$code" == 204 ]] || die "OpenBao refused the write (HTTP $code); nothing was saved"
printf 'Saved in OpenBao (kv/support/intake/%s/%s; the value is not shown).\n' "$COMPANY" "$SOURCE"
printf 'Register the source in the app (Intake sources, step-up) with its allowed IPs.\n'

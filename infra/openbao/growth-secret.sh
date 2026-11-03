#!/usr/bin/env bash
# OWNER ONLY (prompt 21 part 3, contract §29.12): stores the secret of one
# company's growth connection in OpenBao, at kv/hq/growth/<COMPANY>/<KIND>
# (key `secret`): a Google service account's JSON (Search Console,
# Analytics, Play Console), a Telegram bot's token, a YouTube or PageSpeed
# API key, a Bing key. The connection's non-secret config is set in the app;
# the hub reads the figures once a day through egress and shows only whether
# the secret is set, never its value. The app's own route (🔏) does the same.
#   make growth-secret COMPANY=TY KIND=telegram            (paste; input is hidden)
#   make growth-secret COMPANY=TY KIND=ga4 FILE=sa.json    (a service account's JSON file)
# The secret is never printed, never written to disk by this script and never
# put in argv; the server's Claude never runs this.
set -euo pipefail

SECRETS_DIR="${HQ_SECRETS_DIR:-/home/Hub/.secrets}"
ADMIN_FILE="$SECRETS_DIR/openbao-admin.token"
BAO_ADDR="${HQ_BAO_ADDR:-http://127.0.0.1:8200}"
COMPANY="${1:-${COMPANY:-}}"
KIND="${2:-${KIND:-}}"
FILE="${3:-${FILE:-}}"
KINDS="search_console ga4 telegram youtube x pagespeed bing play_console"

die() { printf 'growth-secret: %s\n' "$*" >&2; exit 1; }

[[ -t 0 ]] || die "run this in an interactive terminal (your own SSH session)"
[[ "$COMPANY" =~ ^[A-Z][A-Z0-9]{1,9}$ ]] || die "COMPANY=<CODE> as in the app (e.g. TY)"
[[ " $KINDS " == *" $KIND "* ]] || die "KIND=<kind>, one of: $KINDS (instagram takes none: it is read through IG-Hub)"
[[ -s "$ADMIN_FILE" ]] || die "no OpenBao admin token yet; run 'make up' first"

if [[ -n "$FILE" ]]; then
  [[ -f "$FILE" && -r "$FILE" ]] || die "FILE=$FILE is not a readable file; nothing was saved"
  (($(stat -c %s "$FILE") <= 20000)) || die "the file is larger than 20 000 bytes; nothing was saved"
  secret="$(cat -- "$FILE")"
  jq -e 'type == "object" and has("client_email") and has("private_key")' >/dev/null <<<"$secret" ||
    die "the file is not a Google service account's JSON; nothing was saved"
else
  printf 'Paste the secret of %s / %s (input is hidden), then press Enter:\n> ' "$COMPANY" "$KIND"
  IFS= read -rs secret
  printf '\n'
fi
[[ -n "$secret" ]] || die "nothing was given; nothing was saved"
((${#secret} >= 8 && ${#secret} <= 20000)) || die "a secret is 8 to 20 000 characters; nothing was saved"

umask 077
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
printf 'X-Vault-Token: %s\n' "$(cat "$ADMIN_FILE")" >"$work/auth"
code="$(SEC="$secret" jq -n '{data: {secret: env.SEC}}' |
  curl -sS -o /dev/null -w '%{http_code}' -H @"$work/auth" -H 'Content-Type: application/json' \
    --data-binary @- "$BAO_ADDR/v1/kv/data/hq/growth/$COMPANY/$KIND")"
unset secret
[[ "$code" == 200 || "$code" == 204 ]] || die "OpenBao refused the write (HTTP $code); nothing was saved"
printf 'Saved in OpenBao (kv/hq/growth/%s/%s; the value is not shown).\n' "$COMPANY" "$KIND"
printf 'The hub reads it at the next daily read; press «آزمودن» in the app to read now.\n'

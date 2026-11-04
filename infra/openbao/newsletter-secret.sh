#!/usr/bin/env bash
# OWNER ONLY (prompt 22 part 3, contract §31.3): stores the hub's Listmonk API user in
# OpenBao at kv/hq/newsletter/api (keys `user`, `token`). Create the API user once in
# Listmonk's admin page (Users -> New, type API, a role that may manage lists and
# campaigns), then run in your own terminal:
#   make newsletter-secret USER_NAME=hq-api        (the token is asked for; input is hidden)
# The token is never printed, never written to disk by this script and never put in
# argv; the server's Claude never runs this.
set -euo pipefail

SECRETS_DIR="${HQ_SECRETS_DIR:-/home/Hub/.secrets}"
ADMIN_FILE="$SECRETS_DIR/openbao-admin.token"
BAO_ADDR="${HQ_BAO_ADDR:-http://127.0.0.1:8200}"
NAME="${1:-${USER_NAME:-}}"

die() { printf 'newsletter-secret: %s\n' "$*" >&2; exit 1; }

[[ -t 0 ]] || die "run this in an interactive terminal (your own SSH session)"
[[ "$NAME" =~ ^[A-Za-z0-9._-]{2,64}$ ]] || die "USER_NAME=<the API user's name in Listmonk>"
[[ -s "$ADMIN_FILE" ]] || die "no OpenBao admin token yet; run 'make up' first"

printf 'Paste the API token of %s (input is hidden), then press Enter:\n> ' "$NAME"
IFS= read -rs token
printf '\n'
((${#token} >= 16 && ${#token} <= 200)) || die "a token is 16 to 200 characters; nothing was saved"

umask 077
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
printf 'X-Vault-Token: %s\n' "$(cat "$ADMIN_FILE")" >"$work/auth"
code="$(U="$NAME" T="$token" jq -n '{data: {user: env.U, token: env.T}}' |
  curl -sS -o /dev/null -w '%{http_code}' -H @"$work/auth" -H 'Content-Type: application/json' \
    --data-binary @- "$BAO_ADDR/v1/kv/data/hq/newsletter/api")"
unset token
[[ "$code" == 200 || "$code" == 204 ]] || die "OpenBao refused the write (HTTP $code); nothing was saved"
printf 'Saved in OpenBao (kv/hq/newsletter/api; the token is not shown).\n'

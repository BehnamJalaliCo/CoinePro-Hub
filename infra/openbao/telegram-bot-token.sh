#!/usr/bin/env bash
# OWNER ONLY (prompt 10 §9, §4.2): a support channel's Telegram bot token, at
# kv/support/telegram/<COMPANY>/<CHANNEL> (CHANNEL = telegram_bot |
# telegram_business), with a fresh webhook secret token beside it (Telegram
# sends it back in X-Telegram-Bot-Api-Secret-Token; the hub refuses any update
# without it). Neither is ever printed, written to disk or put in argv.
#   make telegram-bot-token COMPANY=TY CHANNEL=telegram_bot
# The first write is cas 0; replacing a stored token needs REPLACE=yes (the
# webhook must then be set again). Storing a token makes nothing live: the
# channel stays in shadow until the owner seals its support_go_live card.
set -euo pipefail

SECRETS_DIR="${HQ_SECRETS_DIR:-/home/Hub/.secrets}"
ADMIN_FILE="$SECRETS_DIR/openbao-admin.token"
BAO_ADDR="${HQ_BAO_ADDR:-http://127.0.0.1:8200}"
COMPANY="${1:-${COMPANY:-}}"
CHANNEL="${2:-${CHANNEL:-}}"
REPLACE="${REPLACE:-no}"

die() { printf 'telegram-bot-token: %s\n' "$*" >&2; exit 1; }

[[ -t 0 ]] || die "run this in an interactive terminal (your own SSH session)"
[[ "$COMPANY" =~ ^[A-Z][A-Z0-9]{1,9}$ ]] || die "COMPANY=<company code> (e.g. TY)"
[[ "$CHANNEL" == telegram_bot || "$CHANNEL" == telegram_business ]] ||
  die "CHANNEL=telegram_bot or CHANNEL=telegram_business"
[[ -s "$ADMIN_FILE" ]] || die "no OpenBao admin token yet; run 'make up' first"

printf 'Paste the bot token from BotFather for %s/%s (input is hidden), then press Enter:\n> ' \
  "$COMPANY" "$CHANNEL"
IFS= read -rs token
printf '\n'
[[ "$token" =~ ^[0-9]{5,15}:[A-Za-z0-9_-]{30,64}$ ]] || { unset token; die "that is not a bot token; nothing was saved"; }

umask 077
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
printf 'X-Vault-Token: %s\n' "$(cat "$ADMIN_FILE")" >"$work/auth"
opts='{cas: 0}'
[[ "$REPLACE" == yes ]] && opts='{}'
code="$(TOK="$token" HOOK="$(openssl rand -hex 32)" \
  jq -n "{options: $opts, data: {bot_token: env.TOK, webhook_secret: env.HOOK}}" |
  curl -sS -o "$work/resp" -w '%{http_code}' -H @"$work/auth" -H 'Content-Type: application/json' \
    --data-binary @- "$BAO_ADDR/v1/kv/data/support/telegram/$COMPANY/$CHANNEL")"
unset token
if [[ "$code" == 400 ]] && grep -q 'check-and-set' "$work/resp"; then
  die "a token exists already; nothing was changed (REPLACE=yes to replace it)"
fi
[[ "$code" == 200 || "$code" == 204 ]] || die "OpenBao refused the write (HTTP $code); nothing was saved"
printf 'Saved in OpenBao (kv/support/telegram/%s/%s; the values are not shown).\n' "$COMPANY" "$CHANNEL"
printf 'Next: register the intake source in the app; the channel stays in shadow until its go-live card.\n'

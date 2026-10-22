#!/usr/bin/env bash
# OWNER ONLY (prompt 07 §1.3): connects the hourly backup to the owner's Google
# Drive. Run in the owner's own SSH terminal: `make gdrive-auth`.
# The token goes from the hidden prompt straight into OpenBao (kv/backup/gdrive);
# it is never written to disk, never put in argv or in an environment, and
# reaches jq on stdin only (7.1 §3). Both paths keep the scope drive.file:
# rclone's public client, or the owner's own OAuth client through rclone's
# base64 form (7.1 §2.8; the two-argument form would ask for the whole Drive).
set -euo pipefail

BLOG_NAME="gdrive-auth"
# shellcheck source=restic-lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/restic-lib.sh"
ADMIN_FILE="$SECRETS_DIR/openbao-admin.token"

die() { printf 'gdrive-auth: %s\n' "$*" >&2; exit 1; }
[[ -t 0 ]] || die "run this in your own interactive terminal (a person pastes the token)"
[[ -s "$ADMIN_FILE" ]] || die "no OpenBao admin token yet; run make up first"

cat <<'TXT'

اتصال backup ساعتی به Google Drive شما
------------------------------------------------
۱. روی کامپیوتر خودتان (نه این سرور) rclone را نصب کنید: https://rclone.org/downloads/
۲. اگر یک OAuth client ID اختصاصی (نوع Desktop) در Google Cloud خودتان ساخته‌اید (پیشنهاد RUNBOOK؛
   سهمیه‌ی جدا)، client ID آن را همین‌جا بدهید؛ وگرنه فقط Enter بزنید.
   مهم: در آن پروژه، OAuth consent screen باید «In production» باشد؛ در حالت «Testing» گوگل
   refresh token را بعد از ۷ روز باطل میکند و backup بیرونی میایستد.
TXT
printf 'OAuth client ID (Enter = rclone'\''s public client): '
IFS= read -r client_id
client_secret=""
if [[ -n "$client_id" ]]; then
  printf 'OAuth client secret (hidden): '
  IFS= read -rs client_secret
  printf '\n'
  [[ -n "$client_secret" ]] || die "a client ID needs its client secret; nothing was saved"
  blob="$(printf '%s\0%s' "$client_id" "$client_secret" | gdrive_authorize_blob)"
  cat <<'TXT'
۳. این فرمان را روی کامپیوتر خودتان اجرا کنید (client ID، client secret و scope ‏drive.file در
   همین رشته‌ی base64 است: rclone فقط فایل‌هایی را میبیند که خودش ساخته. این رشته را به کسی ندهید):
TXT
  printf '     rclone authorize "drive" "%s"\n' "$blob"
  unset blob
else
  cat <<'TXT'
۳. این فرمان را روی کامپیوتر خودتان اجرا کنید (scope فقط drive.file است: rclone فقط فایل‌هایی را
   میبیند که خودش ساخته):
     rclone authorize "drive" "eyJzY29wZSI6ImRyaXZlLmZpbGUifQ"
TXT
fi
cat <<'TXT'
۴. مرورگر باز میشود؛ با حساب Google خودتان وارد شوید و اجازه بدهید.
۵. rclone یک JSON چاپ میکند که با {"access_token" شروع میشود. همه‌ی آن را کپی کنید
   و پایین بچسبانید (ورودی دیده نمیشود)، بعد Enter.
مقصد: پوشه‌ی CoinePro-HQ/restic در Drive شما. همه‌چیز پیش از ارسال با restic رمزنگاری میشود.

TXT
printf 'Paste the token JSON (hidden), then press Enter:\n> '
IFS= read -rs token
# A long JSON may wrap; one paste delivers every line at once.
while IFS= read -rs -t 1 more; do token+="$more"; done
printf '\n'
token="$(jq -c . <<<"$token" 2>/dev/null)" || die "that is not the JSON rclone printed; nothing was saved"
jq -e 'type == "object" and (.access_token | length > 0) and (.refresh_token | length > 0)' \
  <<<"$token" >/dev/null || die "the JSON has no access_token/refresh_token; nothing was saved"

umask 077
work="$(mktemp -d)"
trap 'rm -rf "$work"; secrets_cleanup' EXIT
printf 'X-Vault-Token: %s\n' "$(cat "$ADMIN_FILE")" >"$work/auth"
# The three values reach jq on stdin, NUL-separated (printf is a shell builtin: no argv).
code="$(printf '%s\0%s\0%s' "$token" "$client_id" "$client_secret" |
  jq -Rsc 'split("\u0000") | {data: {token: .[0], client_id: (.[1] // ""), client_secret: (.[2] // "")}}' |
  curl -sS -o /dev/null -w '%{http_code}' -H @"$work/auth" -H 'Content-Type: application/json' \
    --data-binary @- "$BAO_ADDR/v1/kv/data/backup/gdrive")"
unset token client_secret
[[ "$code" == 200 || "$code" == 204 ]] || die "OpenBao refused the write (HTTP $code); nothing was saved"
printf 'Saved in OpenBao (kv/backup/gdrive). Checking the connection...\n'

compose_facts
load_secrets || die "saved, but the backup's own OpenBao login failed (run make up): $LOAD_ERROR"
if brclone bridge mkdir gdrive:CoinePro-HQ/restic >/dev/null 2>&1; then
  printf 'Google Drive: ok (folder CoinePro-HQ/restic). The next hourly backup copies there.\n'
  printf 'Done - tell Claude on the server that Google Drive is connected.\n'
else
  die "saved, but Google Drive did not answer; check the token and run make gdrive-auth again"
fi

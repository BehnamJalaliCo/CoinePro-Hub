#!/usr/bin/env bash
# OWNER ONLY (prompt 07 §1.3): connects the hourly backup to the owner's Google
# Drive. The owner's way (owner request 2026-10-22: a link and a code, nothing
# to install):
#   make gdrive-auth             the Google link, then the address the browser
#                                ends on (hidden), in the owner's own terminal
#   make gdrive-auth step=link   only the link; the sign-in waits 30 minutes
#   make gdrive-auth step=code   only the address (hidden prompt, or stdin when
#                                the owner hands it to Claude on the server)
#   make gdrive-auth own=1       the owner's own OAuth client: rclone authorize
#                                on the owner's computer, paste its JSON (7.1 §2.8)
# The link flow runs `rclone authorize` in a throwaway backup-tools container
# (hq-gdrive-auth) with rclone's public client and scope drive.file. The
# address carries a one-time code that Google accepts once, within minutes;
# rclone trades it for the token inside the container. The token goes from
# there straight into OpenBao (kv/backup/gdrive): never printed, never written
# to disk, never put in argv or in an environment, and reaches jq on stdin
# only (7.1 §3).
set -euo pipefail

BLOG_NAME="gdrive-auth"
# shellcheck source=restic-lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/restic-lib.sh"
ADMIN_FILE="$SECRETS_DIR/openbao-admin.token"
HELPER="hq-gdrive-auth"
WAIT_S="${HQ_GDRIVE_AUTH_WAIT_S:-1800}"
# rclone's own form of {"scope": "drive.file"}: rclone sees only the files it made.
SCOPE_BLOB="eyJzY29wZSI6ImRyaXZlLmZpbGUifQ"

die() { printf 'gdrive-auth: %s\n' "$*" >&2; exit 1; }
[[ -s "$ADMIN_FILE" ]] || die "no OpenBao admin token yet; run make up first"
step="${1:-}"
case "$step" in "" | link | code) ;; *) die "unknown step '$step' (link | code)" ;; esac

helper_running() { [[ "$(docker inspect -f '{{.State.Running}}' "$HELPER" 2>/dev/null)" == true ]]; }
helper_stop() { if helper_running; then docker stop -t 1 "$HELPER" >/dev/null 2>&1 || true; fi; }

# helper_link: a fresh sign-in (an older one waiting is stopped first) and the
# Google address rclone's local page redirects to, on stdout.
helper_link() {
  local path="" url=""
  helper_stop
  docker run -d --rm --name "$HELPER" --network bridge --memory "$BACKUP_MEM" --user 65534:65534 \
    --cap-drop ALL --security-opt no-new-privileges:true --read-only --tmpfs /tmp:size=16m,mode=1777 \
    -e RCLONE_CONFIG=/tmp/rclone.conf "$BACKUP_IMAGE" \
    sh -c 'busybox timeout "$0" rclone authorize drive "$1" --auth-no-open-browser >/tmp/out 2>&1; sleep 120' \
    "$WAIT_S" "$SCOPE_BLOB" >/dev/null
  for _ in $(seq 1 30); do
    path="$(docker exec "$HELPER" sed -nE 's#.*http://127\.0\.0\.1:53682(/auth\?state=[A-Za-z0-9_-]+).*#\1#p' /tmp/out 2>/dev/null | head -1)"
    [[ -n "$path" ]] && break
    sleep 1
  done
  [[ -n "$path" ]] || { helper_stop; die "rclone did not start the sign-in; nothing was saved"; }
  url="$(printf 'GET %s HTTP/1.0\r\nHost: 127.0.0.1:53682\r\n\r\n' "$path" |
    docker exec -i "$HELPER" busybox nc 127.0.0.1 53682 | tr -d '\r' |
    sed -nE 's#^Location: (https://accounts\.google\.com/.*)$#\1#p')"
  [[ -n "$url" ]] || { helper_stop; die "rclone gave no Google address; nothing was saved"; }
  printf '%s\n' "$url"
}

# helper_code: the address the browser ended on -> rclone's waiting page ->
# the token JSON on stdout (captured by the caller, never shown).
helper_code() {
  local addr="" query="" token=""
  helper_running || die "no sign-in is waiting (it lasts $((WAIT_S / 60)) minutes); run make gdrive-auth step=link again"
  if [[ -t 0 ]]; then
    printf 'Paste the address from the browser (hidden), then press Enter:\n> ' >&2
    IFS= read -rs addr
    printf '\n' >&2
  else
    IFS= read -r addr || true
  fi
  addr="${addr//[[:space:]]/}"
  addr="${addr#http://}"
  addr="${addr#https://}"
  addr="${addr#127.0.0.1:53682}"
  addr="${addr#localhost:53682}"
  addr="${addr#/}"
  query="${addr#\?}"
  [[ "&$query" == *"&code="* && "&$query" == *"&state="* ]] ||
    die "that is not the address after 'Allow' (it starts with 127.0.0.1:53682/?state=); nothing was saved"
  printf 'GET /?%s HTTP/1.0\r\nHost: 127.0.0.1:53682\r\n\r\n' "$query" |
    docker exec -i "$HELPER" busybox nc 127.0.0.1 53682 >/dev/null 2>&1 || true
  unset addr query
  for _ in $(seq 1 30); do
    token="$(docker exec "$HELPER" sed -n '/--->/,/<---End paste/{/--->/d;/<---End paste/d;p}' /tmp/out 2>/dev/null)"
    [[ -n "$token" ]] && break
    docker exec "$HELPER" grep -qE 'ERROR|Failed|wrong state' /tmp/out 2>/dev/null && break
    sleep 1
  done
  helper_stop
  [[ -n "$token" ]] || die "Google did not accept that code (it works once, within minutes); run make gdrive-auth step=link again"
  norm_token "$token"
}

# norm_token RAW: rclone prints the token JSON; some versions print it as
# base64 of {"token": "<JSON>"}. Either way, the token JSON on stdout.
norm_token() {
  local raw="$1" pad
  if jq -e 'type == "object"' <<<"$raw" >/dev/null 2>&1; then printf '%s' "$raw"; return 0; fi
  pad="$(((4 - ${#raw} % 4) % 4))"
  printf '%s%s' "$raw" "$(head -c "$pad" <<<'===')" | tr '_-' '/+' | base64 -d 2>/dev/null |
    jq -c 'if (.token | type) == "string" then (.token | fromjson) else . end' 2>/dev/null || true
}

# save_token TOKEN CLIENT_ID CLIENT_SECRET: checks rclone's JSON, then OpenBao.
save_token() {
  local token client_id="$2" client_secret="$3" code
  token="$(jq -c . <<<"$1" 2>/dev/null)" || die "that is not the JSON rclone printed; nothing was saved"
  jq -e 'type == "object" and (.access_token | length > 0) and (.refresh_token | length > 0)' \
    <<<"$token" >/dev/null || die "the JSON has no access_token/refresh_token; nothing was saved"
  umask 077
  # A global: the EXIT trap runs after this function has returned.
  WORK="$(mktemp -d)"
  trap 'secrets_cleanup; rm -rf "$WORK"' EXIT
  printf 'X-Vault-Token: %s\n' "$(cat "$ADMIN_FILE")" >"$WORK/auth"
  # The three values reach jq on stdin, NUL-separated (printf is a shell builtin: no argv).
  code="$(printf '%s\0%s\0%s' "$token" "$client_id" "$client_secret" |
    jq -Rsc 'split("\u0000") | {data: {token: .[0], client_id: (.[1] // ""), client_secret: (.[2] // "")}}' |
    curl -sS -o /dev/null -w '%{http_code}' -H @"$WORK/auth" -H 'Content-Type: application/json' \
      --data-binary @- "$BAO_ADDR/v1/kv/data/backup/gdrive")"
  [[ "$code" == 200 || "$code" == 204 ]] || die "OpenBao refused the write (HTTP $code); nothing was saved"
  printf 'Saved in OpenBao (kv/backup/gdrive). Checking the connection...\n'
  load_secrets || die "saved, but the backup's own OpenBao login failed (run make up): $LOAD_ERROR"
  if brclone bridge mkdir gdrive:CoinePro-HQ/restic >/dev/null 2>&1; then
    printf 'Google Drive: ok (folder CoinePro-HQ/restic). The next hourly backup copies there.\n'
    printf 'Done - tell Claude on the server that Google Drive is connected.\n'
  else
    die "saved, but Google Drive did not answer; check the token and run make gdrive-auth again"
  fi
}

compose_facts

# ---------------------------------------------------------------- own client --
if [[ -n "${GDRIVE_OWN_CLIENT:-}" ]]; then
  [[ -t 0 ]] || die "run this in your own interactive terminal (a person pastes the token)"
  cat <<'TXT'

اتصال backup ساعتی به Google Drive، با OAuth client اختصاصی خودتان
------------------------------------------------
۱. روی کامپیوتر خودتان (نه این سرور) rclone را نصب کنید: https://rclone.org/downloads/
۲. client ID و client secret همان OAuth client (نوع Desktop) را بدهید.
   مهم: در آن پروژه، OAuth consent screen باید «In production» باشد؛ در حالت «Testing» گوگل
   refresh token را بعد از ۷ روز باطل میکند و backup بیرونی میایستد.
TXT
  printf 'OAuth client ID: '
  IFS= read -r client_id
  [[ -n "$client_id" ]] || die "no client ID; for rclone's public client run make gdrive-auth"
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
  cat <<'TXT'
۴. مرورگر باز میشود؛ با حساب Google خودتان وارد شوید و اجازه بدهید.
۵. rclone یک JSON چاپ میکند که با {"access_token" شروع میشود. همه‌ی آن را کپی کنید
   و پایین بچسبانید (ورودی دیده نمیشود)، بعد Enter.

TXT
  printf 'Paste the token JSON (hidden), then press Enter:\n> '
  IFS= read -rs token
  # A long JSON may wrap; one paste delivers every line at once.
  while IFS= read -rs -t 1 more; do token+="$more"; done
  printf '\n'
  save_token "$token" "$client_id" "$client_secret"
  exit 0
fi

# ----------------------------------------------------------- link and code --
if [[ "$step" != code ]]; then
  [[ -n "$step" || -t 0 ]] || die "run this in your own interactive terminal, or use step=link and step=code"
  # In one go, a sign-in left waiting is stopped on the way out.
  if [[ -z "$step" ]]; then trap helper_stop EXIT; fi
  url="$(helper_link)"
  cat <<'TXT'

اتصال backup ساعتی به Google Drive شما
------------------------------------------------
۱. این لینک را روی گوشی یا کامپیوتر خودتان باز کنید، با حساب Google وارد شوید و «Allow» بزنید.
   (دسترسی فقط drive.file است: rclone فقط فایل‌هایی را میبیند که خودش ساخته.)
۲. بعد از Allow، مرورگر به صفحه‌ای میرود که باز نمیشود (127.0.0.1:53682). این درست است.
   همه‌ی آدرس نوار بالای همان صفحه را کپی کنید.
مقصد: پوشه‌ی CoinePro-HQ/restic در Drive شما. همه‌چیز پیش از ارسال با restic رمزنگاری میشود.

TXT
  printf '%s\n\n' "$url"
  if [[ "$step" == link ]]; then
    printf 'The sign-in waits %d minutes. Then: make gdrive-auth step=code\n' "$((WAIT_S / 60))"
    exit 0
  fi
fi
token="$(helper_code)"
save_token "$token" "" ""

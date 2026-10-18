#!/usr/bin/env bash
# OWNER ONLY (prompt 09 §1): adds one of the owner's PUBLIC SSH keys to the
# list a new server gets for its work user (kv/provisioning/ssh-keys). Not a
# secret, but only the owner gives it; several keys are allowed; a private key
# is refused (and never stored).
#   make owner-ssh-key          (paste the public key, e.g. ~/.ssh/id_ed25519.pub)
set -euo pipefail

SECRETS_DIR="${HQ_SECRETS_DIR:-/home/Hub/.secrets}"
ADMIN_FILE="$SECRETS_DIR/openbao-admin.token"
BAO_ADDR="${HQ_BAO_ADDR:-http://127.0.0.1:8200}"

die() { printf 'owner-ssh-key: %s\n' "$*" >&2; exit 1; }

[[ -t 0 ]] || die "run this in an interactive terminal (your own SSH session)"
[[ -s "$ADMIN_FILE" ]] || die "no OpenBao admin token yet; run 'make up' first"

cat <<'TEXT'
کلید عمومی SSH خودتان را بچسبانید (یک خط، مثل محتوای ~/.ssh/id_ed25519.pub).
فقط کلید عمومی؛ کلید خصوصی رد میشود و هیچ‌جا ذخیره نمیشود.
TEXT
printf '> '
IFS= read -r key
key="${key%$'\r'}"
case "$key" in
  *PRIVATE*) die "that is a PRIVATE key: never paste it anywhere; nothing was saved" ;;
esac
[[ "$key" =~ ^(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp(256|384|521)|sk-ssh-ed25519@openssh\.com|sk-ecdsa-sha2-nistp256@openssh\.com)\ [A-Za-z0-9+/=]+(\ .*)?$ ]] ||
  die "not a public SSH key line; nothing was saved"
((${#key} <= 2000)) || die "longer than 2000 characters; nothing was saved"

umask 077
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
printf '%s\n' "$key" >"$work/key.pub"
fp="$(ssh-keygen -l -f "$work/key.pub" 2>/dev/null)" || die "ssh-keygen does not read it as a public key; nothing was saved"

printf 'X-Vault-Token: %s\n' "$(cat "$ADMIN_FILE")" >"$work/auth"
code="$(curl -sS -o "$work/cur" -w '%{http_code}' -H @"$work/auth" "$BAO_ADDR/v1/kv/data/provisioning/ssh-keys")"
case "$code" in
  200) jq -c '.data.data.keys // []' "$work/cur" >"$work/keys" ;;
  404) echo '[]' >"$work/keys" ;;
  *) die "OpenBao answered HTTP $code; nothing was saved" ;;
esac
K="$key" jq -c '. as $k | if index(env.K) then $k else $k + [env.K] end' "$work/keys" >"$work/new"
if cmp -s "$work/keys" "$work/new"; then
  printf 'This key is already there: %s\n' "$fp"
  exit 0
fi
code="$(jq '{data: {keys: .}}' "$work/new" |
  curl -sS -o /dev/null -w '%{http_code}' -H @"$work/auth" -H 'Content-Type: application/json' \
    --data-binary @- "$BAO_ADDR/v1/kv/data/provisioning/ssh-keys")"
[[ "$code" == 200 || "$code" == 204 ]] || die "OpenBao refused the write (HTTP $code); nothing was saved"
printf 'Saved (kv/provisioning/ssh-keys, %s key(s) now): %s\n' "$(jq length "$work/new")" "$fp"

#!/usr/bin/env bash
# OWNER ONLY (prompt 09 §1): stores the Hetzner Cloud API token of the project
# the new companies' servers are made in (Read & Write) in OpenBao, at
# kv/provisioning/hetzner. Only the provisioner reads it, at the moment of
# work; no agent, model, log or API ever sees it.
#   make hetzner-token        (paste; input is hidden)
# The token is never printed, never written to disk and never put in argv.
set -euo pipefail

SECRETS_DIR="${HQ_SECRETS_DIR:-/home/Hub/.secrets}"
ADMIN_FILE="$SECRETS_DIR/openbao-admin.token"
BAO_ADDR="${HQ_BAO_ADDR:-http://127.0.0.1:8200}"
HETZNER_API="${HQ_HETZNER_API:-https://api.hetzner.cloud/v1}"

die() { printf 'hetzner-token: %s\n' "$*" >&2; exit 1; }

[[ -t 0 ]] || die "run this in an interactive terminal (your own SSH session)"
[[ -s "$ADMIN_FILE" ]] || die "no OpenBao admin token yet; run 'make up' first"

cat <<'TEXT'
توکن API پروژه‌ی هتزنر (Read & Write) را بچسبانید. این همان پروژه‌ای است که
سرورهای شرکت‌های تازه در آن ساخته میشوند. ورودی دیده نمیشود و توکن مستقیم
در OpenBao میرود. هاب فقط منابعی را که خودش با برچسب managed-by=coinepro-hq
میسازد لمس میکند؛ هیچ سرور، فایروال یا شبکه‌ی موجودی تغییر نمیکند.
TEXT
printf '> '
IFS= read -rs token
printf '\n'
[[ -n "$token" ]] || die "nothing was pasted; nothing was saved"
[[ "$token" =~ ^[A-Za-z0-9]{40,100}$ ]] || die "that does not look like a Hetzner API token; nothing was saved"

umask 077
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
# A read-only check that the token works (the project's locations), before saving it.
printf 'Authorization: Bearer %s\n' "$token" >"$work/hz"
code="$(curl -sS -o /dev/null -w '%{http_code}' -H @"$work/hz" "$HETZNER_API/locations" || true)"
rm -f "$work/hz"
[[ "$code" == 200 ]] || die "Hetzner did not accept the token (HTTP $code); nothing was saved"

printf 'X-Vault-Token: %s\n' "$(cat "$ADMIN_FILE")" >"$work/auth"
code="$(T="$token" jq -n '{data: {token: env.T}}' |
  curl -sS -o /dev/null -w '%{http_code}' -H @"$work/auth" -H 'Content-Type: application/json' \
    --data-binary @- "$BAO_ADDR/v1/kv/data/provisioning/hetzner")"
unset token
[[ "$code" == 200 || "$code" == 204 ]] || die "OpenBao refused the write (HTTP $code); nothing was saved"
printf 'Saved in OpenBao (kv/provisioning/hetzner; the value is not shown).\n'
printf 'Next: make owner-ssh-key, then HQ_PROVISIONING=on in infra/compose/.env and make up.\n'

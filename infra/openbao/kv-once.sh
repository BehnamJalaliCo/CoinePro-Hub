#!/usr/bin/env bash
# A generated secret in OpenBao, made once and never replaced (prompt 10 §1.2:
# kv/support/pseudonym, the customer pseudonym's HMAC key; a new key would make
# every past subject a stranger). Run by provision.sh (`make up`) with its admin
# token's header file. As restic-password.sh (7.1 §2.9): only HTTP 404 reads as
# "absent", and the write is a KV check-and-set with cas 0, so OpenBao itself
# refuses it whenever a version exists, whatever an earlier read answered.
# Never printed: the value goes from openssl to jq to curl through pipes only.
#
#   kv-once.sh AUTH_HEADER_FILE KV_PATH FIELD      (env HQ_BAO_ADDR)
#   e.g. kv-once.sh "$auth" support/pseudonym key  -> 32 random bytes, hex
set -euo pipefail

BAO_ADDR="${HQ_BAO_ADDR:-http://127.0.0.1:8200}"
usage="usage: kv-once.sh AUTH_HEADER_FILE KV_PATH FIELD"
auth="${1:?$usage}"
path="${2:?$usage}"
field="${3:?$usage}"
if [[ ! "$path" =~ ^[a-z0-9][a-z0-9/_-]{0,100}$ || ! "$field" =~ ^[a-z][a-z0-9_]{0,40}$ ]]; then
  echo "kv-once: bad path or field" >&2
  exit 2
fi
log() { printf 'openbao-provision: %s: %s\n' "$path" "$*"; }

code="$(curl -sS -o /dev/null -w '%{http_code}' -H @"$auth" "$BAO_ADDR/v1/kv/data/$path" 2>/dev/null)" ||
  code="${code:-000}"
case "$code" in
  200) exit 0 ;;
  404) ;;
  *)
    log "OpenBao answered HTTP $code; nothing created"
    exit 1
    ;;
esac

umask 077
resp="$(mktemp)"
trap 'rm -f "$resp"' EXIT
code="$(openssl rand -hex 32 | tr -d '\n' | jq -Rsc --arg f "$field" '{options: {cas: 0}, data: {($f): .}}' |
  curl -sS -o "$resp" -w '%{http_code}' -H @"$auth" -H 'Content-Type: application/json' \
    --data-binary @- "$BAO_ADDR/v1/kv/data/$path" 2>/dev/null)" || code="${code:-000}"
case "$code" in
  200 | 204) log "created (never printed)" ;;
  400)
    # The only 400 a cas-0 write of this body gets: the key already has a version.
    if grep -q 'check-and-set' "$resp"; then
      log "already exists (check-and-set refused the write); kept"
    else
      log "OpenBao refused the write (HTTP 400)"
      exit 1
    fi
    ;;
  *)
    log "OpenBao refused the write (HTTP $code)"
    exit 1
    ;;
esac

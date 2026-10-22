#!/usr/bin/env bash
# The restic repositories' password (local, Google Drive, Hetzner) in OpenBao
# (kv/backup/restic), made once and kept: changing it would lock every
# existing snapshot. Run by provision.sh (`make up`) with its admin token's
# header file. 7.1 §2.9: only HTTP 404 reads as "absent", and the write is a
# KV check-and-set with cas 0, so OpenBao itself refuses it whenever a
# password exists, whatever an earlier read answered (a 503 or a lost answer
# once read as "absent" would have made a new password). Never printed: the
# new password goes from openssl to jq to curl through pipes only.
#
#   restic-password.sh AUTH_HEADER_FILE      (env HQ_BAO_ADDR)
set -euo pipefail

BAO_ADDR="${HQ_BAO_ADDR:-http://127.0.0.1:8200}"
auth="${1:?usage: restic-password.sh AUTH_HEADER_FILE}"
log() { printf 'openbao-provision: backup: %s\n' "$*"; }

code="$(curl -sS -o /dev/null -w '%{http_code}' -H @"$auth" "$BAO_ADDR/v1/kv/data/backup/restic" 2>/dev/null)" ||
  code="${code:-000}"
case "$code" in
  200) exit 0 ;;
  404) ;;
  *)
    log "OpenBao answered HTTP $code for kv/backup/restic; no password created"
    exit 1
    ;;
esac

umask 077
resp="$(mktemp)"
trap 'rm -f "$resp"' EXIT
code="$(openssl rand -base64 48 | tr -d '\n' | jq -Rsc '{options: {cas: 0}, data: {password: .}}' |
  curl -sS -o "$resp" -w '%{http_code}' -H @"$auth" -H 'Content-Type: application/json' \
    --data-binary @- "$BAO_ADDR/v1/kv/data/backup/restic" 2>/dev/null)" || code="${code:-000}"
case "$code" in
  200 | 204) log "restic repository password created (kv/backup/restic; never printed)" ;;
  400)
    # The only 400 a cas-0 write of this body gets: the key already has a version.
    if grep -q 'check-and-set' "$resp"; then
      log "kv/backup/restic already exists (check-and-set refused the write); kept"
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

#!/usr/bin/env bash
# OWNER ONLY (prompt 07 §1.2): stores the owner's OpenBao snapshot-only token
# for the hourly raft snapshot (kv/backup/openbao-snapshot). The server never
# creates this token; the owner creates it in their own terminal:
#   bao token create -policy=backup-snapshot -orphan -period=768h -display-name=hq-backup-snapshot
# (policy infra/openbao/policies/backup-snapshot.hcl, loaded by make up), then
# runs `make openbao-snapshot-token` and pastes it (hidden). Never printed.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SECRETS_DIR="${HQ_SECRETS_DIR:-/home/Hub/.secrets}"
ADMIN_FILE="$SECRETS_DIR/openbao-admin.token"
BAO_ADDR="${HQ_BAO_ADDR:-http://127.0.0.1:8200}"

die() { printf 'openbao-snapshot-token: %s\n' "$*" >&2; exit 1; }
[[ -t 0 ]] || die "run this in your own interactive terminal (a person pastes the token)"
[[ -s "$ADMIN_FILE" ]] || die "no OpenBao admin token yet; run make up first"
[[ -r "$REPO_DIR/infra/openbao/policies/backup-snapshot.hcl" ]] || die "policy file missing"

printf 'Paste the snapshot-only token (hidden), then press Enter:\n> '
IFS= read -rs token
printf '\n'
token="${token//[[:space:]]/}"
[[ -n "$token" ]] || die "nothing was pasted"
[[ "$token" =~ ^[A-Za-z0-9._-]+$ ]] || die "an OpenBao token has only letters, digits, '.', '-' and '_'; nothing was saved"

umask 077
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
# The token must hold exactly the backup-snapshot policy (never more).
printf 'X-Vault-Token: %s\n' "$token" >"$work/self"
policies="$(curl -sS -f -H @"$work/self" "$BAO_ADDR/v1/auth/token/lookup-self" 2>/dev/null |
  jq -c '[.data.policies[] | select(. != "default")] | sort' 2>/dev/null || true)"
[[ "$policies" == '["backup-snapshot"]' ]] ||
  die "that token's policies are ${policies:-unknown}; create one with only backup-snapshot; nothing was saved"
printf 'X-Vault-Token: %s\n' "$(cat "$ADMIN_FILE")" >"$work/auth"
code="$(TOK="$token" jq -n '{data: {token: env.TOK}}' |
  curl -sS -o /dev/null -w '%{http_code}' -H @"$work/auth" -H 'Content-Type: application/json' \
    --data-binary @- "$BAO_ADDR/v1/kv/data/backup/openbao-snapshot")"
unset token
[[ "$code" == 200 || "$code" == 204 ]] || die "OpenBao refused the write (HTTP $code); nothing was saved"
printf 'Saved (kv/backup/openbao-snapshot). The next hourly backup includes the OpenBao snapshot.\n'

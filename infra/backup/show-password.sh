#!/usr/bin/env bash
# OWNER ONLY (prompt 07 §1.2): shows the restic repository password once, in
# the owner's own terminal, for the paper copy (`make backup-password`). Without
# it no snapshot can ever be opened, from any destination. Refuses without a
# terminal (a pipe, a timer, an agent) and clears the screen after Enter.
set -euo pipefail

SECRETS_DIR="${HQ_SECRETS_DIR:-/home/Hub/.secrets}"
ADMIN_FILE="$SECRETS_DIR/openbao-admin.token"
BAO_ADDR="${HQ_BAO_ADDR:-http://127.0.0.1:8200}"

die() { printf 'backup-password: %s\n' "$*" >&2; exit 1; }
[[ -t 0 && -t 1 ]] || die "only in your own interactive terminal"
[[ -s "$ADMIN_FILE" ]] || die "no OpenBao admin token yet; run make up first"
printf 'Type "show" to display the restic password for your paper copy: '
IFS= read -r answer
[[ "$answer" == show ]] || die "not shown"

umask 077
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
printf 'X-Vault-Token: %s\n' "$(cat "$ADMIN_FILE")" >"$work/auth"
curl -sS -f -H @"$work/auth" "$BAO_ADDR/v1/kv/data/backup/restic" -o "$work/r" 2>/dev/null ||
  die "OpenBao did not answer (sealed?)"
printf '\n  restic password:  %s\n\n' "$(jq -r '.data.data.password // "(none: run make up)"' "$work/r")"
printf 'Write it down on paper and keep it safe. Press Enter to clear the screen. '
IFS= read -r _
clear 2>/dev/null || printf '\033[2J\033[H'

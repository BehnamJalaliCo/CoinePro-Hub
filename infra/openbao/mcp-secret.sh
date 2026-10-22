#!/usr/bin/env bash
# OWNER ONLY (prompt 07 §3, 7.1 §2.15): the secret of one MCP server (an API
# key or a token the server wants in its auth header, or a whole JSON key such
# as a Google service account's) into OpenBao, at kv/hq-api/tools/mcp/<KEY>,
# where the api reads it for one call at a time.
#   make mcp-secret KEY=<server key>                 (paste; input is hidden)
#   make mcp-secret KEY=<server key> FILE=<path>     (a JSON file: checked to be a
#                                                     JSON object, stored as it is)
# The value is never printed, never written to disk by this script and never
# put in argv or the environment (it reaches jq and curl on stdin); nobody
# reads it back through the API (GET /tools/mcp only says has_secret). After
# a FILE, delete the file: OpenBao holds it now.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SECRETS_DIR="${HQ_SECRETS_DIR:-/home/Hub/.secrets}"
ADMIN_FILE="$SECRETS_DIR/openbao-admin.token"
BAO_ADDR="${HQ_BAO_ADDR:-http://127.0.0.1:8200}"
KEY="${1:-}"
FILE="${2:-}"
MAX_FILE=65536

die() { printf 'mcp-secret: %s\n' "$*" >&2; exit 1; }

[[ "$KEY" =~ ^[a-z][a-z0-9-]{1,39}$ ]] || die "usage: make mcp-secret KEY=<server key, as registered> [FILE=<json file>]"
[[ -t 0 ]] || die "run this in an interactive terminal"
[[ -s "$ADMIN_FILE" ]] || die "no OpenBao admin token yet; run 'make up' first"
cd "$REPO_DIR"

umask 077
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
printf 'X-Vault-Token: %s\n' "$(cat "$ADMIN_FILE")" >"$work/auth"

# The JSON body on stdin -> OpenBao; prints the HTTP status.
put() {
  curl -sS -o /dev/null -w '%{http_code}' -H @"$work/auth" -H 'Content-Type: application/json' \
    --data-binary @- "$BAO_ADDR/v1/kv/data/hq-api/tools/mcp/$KEY"
}

if [[ -n "$FILE" ]]; then
  [[ -f "$FILE" && -r "$FILE" ]] || die "FILE is not a readable file; nothing was saved"
  size="$(stat -c %s -- "$FILE")"
  ((size > 0)) || die "the file is empty; nothing was saved"
  ((size <= MAX_FILE)) || die "the file is larger than $MAX_FILE bytes; nothing was saved"
  # A JSON object (a service account key is one); jq's error would quote the
  # text, so only its exit code is used.
  jq -e 'type == "object"' <"$FILE" >/dev/null 2>&1 || die "the file is not a JSON object; nothing was saved"
  # Stored as it is: the file's exact text is the secret.
  code="$(jq -Rs '{data: {token: .}}' <"$FILE" | put)"
else
  printf 'Paste the secret of MCP server "%s" (input is hidden), then press Enter:\n> ' "$KEY"
  IFS= read -rs secret
  printf '\n'
  secret="${secret//[[:space:]]/}"
  [[ -n "$secret" ]] || die "nothing was pasted; nothing was saved"
  ((${#secret} <= 4096)) || die "that is longer than 4096 characters; nothing was saved (a JSON key: FILE=<path>)"
  code="$(printf '%s' "$secret" | jq -Rs '{data: {token: .}}' | put)" # printf is a builtin: no argv
  unset secret
fi
[[ "$code" == 200 || "$code" == 204 ]] || die "OpenBao refused the write (HTTP $code); nothing was saved"
printf 'Saved in OpenBao (kv/hq-api/tools/mcp/%s). The next call of that server uses it.\n' "$KEY"
if [[ -n "$FILE" ]]; then
  printf 'The file still holds the key. Delete it now that OpenBao has it, e.g.: shred -u -- %q\n' "$FILE"
fi

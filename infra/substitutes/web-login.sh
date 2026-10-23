#!/usr/bin/env bash
# OWNER ONLY, in the owner's own terminal (prompt 12 §9.1.5, contract §21.13):
# sign in once to ChatGPT, Gemini or DeepSeek in the hub's browser profile for
# that account. A visible browser for at most 15 minutes, shown by noVNC on
# this server's 127.0.0.1:6080 only; reach it with your own SSH tunnel
# (ssh -L 6080:127.0.0.1:6080 ...). The server's SSH configuration is not
# touched. The hub never sees your password. Claude never runs it.
# Usage: web-login.sh chatgpt-web|gemini-web|deepseek-web
set -euo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HQ="$REPO_DIR/infra/compose/hq.sh"
account="${1:-}"
case "$account" in
  chatgpt-web | gemini-web | deepseek-web) ;;
  *) echo "usage: $0 chatgpt-web|gemini-web|deepseek-web" >&2; exit 2 ;;
esac
[[ -t 1 ]] || { echo "error: run this in your own terminal" >&2; exit 2; }
cleanup() { "$HQ" --profile web-login rm -sf web-login-relay >/dev/null 2>&1 || true; }
trap cleanup EXIT
# The window's image (also the relay's): built here, so a fresh machine or a
# changed sign-in script never needs a pull (14.1 §1.3; the cache makes it quick).
"$HQ" --profile web-login build browser-web-login
"$HQ" --profile web-login up -d web-login-relay
since="$(date +%s)"
"$HQ" --profile web-login run --rm --name coinepro-hq-web-login browser-web-login "$account"
# Tell the hub, once the profile really holds this sign-in (14.1).
"$REPO_DIR/infra/substitutes/report-signin.sh" web "$account" "$since" || true

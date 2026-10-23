#!/usr/bin/env bash
# OWNER ONLY, in the owner's own terminal (prompt 12 §9.1.6, contract §21.13):
# the official CLI's own sign-in, into the runner's sign-in volume
# (hq-substitute-auth, files 600, not in the backups). Claude never runs it.
#   codex:  "Sign in with ChatGPT" by device code (open the link on your phone, enter the code)
#   gemini: discontinued by Google for individuals (contract ⟨1.7.2⟩): make gemini-web-login
# The CLI reaches only its own hosts, through egress (the runner's network).
# The same sign-in is also offered from the app (Settings → Connections).
# Usage: cli-login.sh codex|gemini
set -euo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HQ="$REPO_DIR/infra/compose/hq.sh"
[[ -t 0 && -t 1 ]] || { echo "error: run this in your own terminal (it is interactive)" >&2; exit 2; }
case "${1:-}" in
  codex)
    echo "ChatGPT (Codex CLI): a link and a one-time code follow; sign in on your phone."
    exec "$HQ" --profile substitutes run --rm --entrypoint sh substitute-runner -c \
      'umask 077; mkdir -p /auth/codex; CODEX_HOME=/auth/codex HOME=/work exec codex login --device-auth'
    ;;
  gemini)
    # Contract ⟨1.7.2⟩ (14.1 §2.2): Google ended this sign-in for individuals.
    echo "Gemini CLI for individuals is discontinued by Google; Gemini runs through make gemini-web-login"
    ;;
  *) echo "usage: $0 codex|gemini" >&2; exit 2 ;;
esac

#!/usr/bin/env bash
# Prompt 14.1: after the owner's own sign-in (`make <x>-web-login`, `make
# chatgpt-login`), tell the hub, once the sign-in is really there: the
# account's browser profile has cookies written during this sign-in, or
# Codex's auth file exists. Uses the substitutes dispatcher's token (the same
# internal route family as its jobs); prints only the outcome, never a cookie
# or a token.
# Usage: report-signin.sh web <chatgpt-web|gemini-web|deepseek-web> [since-epoch]
#        report-signin.sh cli codex
set -euo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HQ="$REPO_DIR/infra/compose/hq.sh"
SECRETS_DIR="${HQ_SECRETS_DIR:-/home/Hub/.secrets}"
AUTH_FILE="$SECRETS_DIR/substitutes/api-auth"
CURL_IMAGE="curlimages/curl:8.17.0"
via="${1:-}"
what="${2:-}"
since="${3:-0}"
case "$via:$what" in
  web:chatgpt-web) player=gpt ;;
  web:gemini-web) player=gemini ;;
  web:deepseek-web) player=deepseek ;;
  cli:codex) player=gpt ;;
  *) echo "usage: $0 web chatgpt-web|gemini-web|deepseek-web [since] | cli codex" >&2; exit 2 ;;
esac
[[ "$since" =~ ^[0-9]+$ ]] || since=0
if [[ ! -r "$AUTH_FILE" ]]; then
  echo "The hub could not be told (no dispatcher token yet: make up with HQ_SUBSTITUTES=on)." >&2
  exit 1
fi
# shellcheck disable=SC2016 # the container's own shell expands these
if [[ "$via" == web ]]; then
  # The profile's cookie store, written at or after the window opened.
  ok="$("$HQ" --profile web-login run --rm --no-deps -T --entrypoint sh browser-web-login -c \
    'c="/profiles/$1/Default/Cookies"; [ -s "$c" ] && [ "$(stat -c %Y "$c")" -ge "$2" ] && echo yes || echo no' \
    sh "$what" "$since" 2>/dev/null | tail -n1)"
else
  ok="$("$HQ" --profile substitutes run --rm --no-deps -T --entrypoint sh substitute-runner -c \
    '[ -s /auth/codex/auth.json ] && echo yes || echo no' 2>/dev/null | tail -n1)"
fi
if [[ "$ok" != yes ]]; then
  echo "No sign-in found for $what; the hub still shows it signed out. Run the sign-in again."
  exit 1
fi
code="$(printf '{"player":"%s","via":"%s"}' "$player" "$via" |
  docker run --rm -i --init --network hq-internal --read-only --cap-drop ALL \
    --security-opt no-new-privileges:true --user "$(id -u):$(id -g)" --memory 32m \
    -v "$AUTH_FILE:/run/auth:ro" --entrypoint timeout "$CURL_IMAGE" \
    45 curl -sS -m 30 -o /dev/null -w '%{http_code}' -X POST -H @/run/auth -H 'Content-Type: application/json' \
    --data-binary @- "http://api:8000/internal/v1/substitutes/signed-in" || true)"
if [[ "$code" == 200 ]]; then
  echo "The hub now shows $what as signed in."
else
  echo "The sign-in is there, but the hub did not take it (HTTP ${code:-none})." >&2
  exit 1
fi

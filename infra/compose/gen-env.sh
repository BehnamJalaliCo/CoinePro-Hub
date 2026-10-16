#!/usr/bin/env bash
# Creates infra/compose/.env from .env.example: every *_PASSWORD gets a fresh
# 256-bit random value, everything else stays empty (compose defaults apply).
# On an existing file it only appends keys that are missing (new prompts).
# Never prints a value and never changes an existing line.
#
# Usage: gen-env.sh [--output PATH]
set -euo pipefail

COMPOSE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXAMPLE="$COMPOSE_DIR/.env.example"
OUTPUT="$COMPOSE_DIR/.env"

while (($#)); do
  case "$1" in
    --output) OUTPUT="$2"; shift 2 ;;
    *) echo "error: unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [[ -e "$OUTPUT" ]]; then
  # Add keys introduced by later prompts; existing lines are never changed.
  added=()
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ "$line" =~ ^([A-Z0-9_]+)=$ ]] || continue
    key="${BASH_REMATCH[1]}"
    grep -q "^${key}=" "$OUTPUT" && continue
    if [[ "$key" == *_PASSWORD ]]; then
      printf '%s=%s\n' "$key" "$(openssl rand -hex 32)" >>"$OUTPUT"
    else
      printf '%s=\n' "$key" >>"$OUTPUT"
    fi
    added+=("$key")
  done <"$EXAMPLE"
  if ((${#added[@]})); then
    echo "env: added ${added[*]} to $OUTPUT (values not shown)"
  fi
  exit 0
fi

umask 077
tmp="$(mktemp "$(dirname "$OUTPUT")/.env.tmp.XXXXXX")"
trap 'rm -f "$tmp"' EXIT

while IFS= read -r line || [[ -n "$line" ]]; do
  if [[ "$line" =~ ^([A-Z0-9_]+_PASSWORD)=$ ]]; then
    printf '%s=%s\n' "${BASH_REMATCH[1]}" "$(openssl rand -hex 32)"
  else
    printf '%s\n' "$line"
  fi
done <"$EXAMPLE" >"$tmp"

chmod 600 "$tmp"
mv "$tmp" "$OUTPUT"
trap - EXIT
echo "env: created $OUTPUT (mode 600, values not shown)"

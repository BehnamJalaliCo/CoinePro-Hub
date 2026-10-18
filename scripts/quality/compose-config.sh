#!/usr/bin/env bash
# `docker compose config -q` for every profile.
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
ensure_env

for profile in "${PROFILES[@]}"; do
  # A comment glued to its value (`X=1#note`) is part of the value: Go rejected
  # GOMEMLIMIT_TEMPORAL=610MiB#... at start (prompt 07 merge). Comments need a space.
  if grep -nE '^[A-Z0-9_]+=[^ #]+#' "$REPO_DIR/infra/compose/profiles/$profile.env"; then
    echo "compose-config: $profile: a comment glued to a value (put a space before #)" >&2
    exit 1
  fi
  HQ_PROFILE="$profile" "$HQ" config -q
  echo "compose-config: $profile ok"
done

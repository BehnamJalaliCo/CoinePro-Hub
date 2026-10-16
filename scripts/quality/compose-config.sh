#!/usr/bin/env bash
# `docker compose config -q` for every profile.
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
ensure_env

for profile in "${PROFILES[@]}"; do
  HQ_PROFILE="$profile" "$HQ" config -q
  echo "compose-config: $profile ok"
done

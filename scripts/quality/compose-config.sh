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

# Review 9.2: HQ_PROVISIONING stays off by default. With a fresh secrets
# file (gen-env.sh, as a new server gets it) and nothing in the environment,
# the provisioner (the only reader of the Hetzner token) is not in the model
# and the api has no PROVISIONER_URL (nothing priced, listed or built).
default_env="$(mktemp)"
"$REPO_DIR/infra/compose/gen-env.sh" --output "$default_env" >/dev/null
for profile in "${PROFILES[@]}"; do
  off="$(env -u HQ_PROVISIONING HQ_ENV_FILE="$default_env" HQ_PROFILE="$profile" HQ_STT=off \
    "$HQ" config --format json | jq -r '[(.services | has("provisioner")),
      (.services.api.environment.PROVISIONER_URL // "")] | @tsv')"
  if [[ "$off" != $'false\t' ]]; then
    rm -f "$default_env"
    echo "compose-config: $profile: the provisioner is on by default ($off)" >&2
    exit 1
  fi
done
rm -f "$default_env"
echo "compose-config: the provisioner is off by default"

#!/usr/bin/env bash
# Sum of all container memory limits <= 80% of RAM, per profile (prompt 03;
# 60% held for the platform alone in prompt 02).
# Each profile is checked against its reference RAM (profiles/<p>.env:
# HQ_BUDGET_REF_RAM_MB); on the server the active profile is also checked
# against the real MemTotal.
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
ensure_env

PERCENT=80
failed=0

limit_sum_mb() {
  compose_json "$1" | jq '[.services[].deploy.resources.limits.memory | tonumber] | add / 1048576 | floor'
}

check() { # profile ram_mb label
  local sum budget
  sum="$(limit_sum_mb "$1")"
  budget=$(($2 * PERCENT / 100))
  if ((sum <= budget)); then
    echo "memory-budget: $1 ok ($sum MiB <= $budget MiB = ${PERCENT}% of $2 MiB $3)"
  else
    echo "memory-budget: $1 OVER ($sum MiB > $budget MiB = ${PERCENT}% of $2 MiB $3)" >&2
    failed=1
  fi
}

for profile in "${PROFILES[@]}"; do
  ref="$(sed -n 's/^HQ_BUDGET_REF_RAM_MB=//p' "$REPO_DIR/infra/compose/profiles/$profile.env")"
  check "$profile" "$ref" "reference"
done

if [[ -z "${CI:-}" && -r /proc/meminfo ]]; then
  active="$("$HQ" --print-profile)"
  check "$active" "$(awk '/^MemTotal:/ {print int($2 / 1024)}' /proc/meminfo)" "this server"
fi
exit "$failed"

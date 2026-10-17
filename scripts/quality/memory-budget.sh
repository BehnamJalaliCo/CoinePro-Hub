#!/usr/bin/env bash
# Sum of all container memory limits <= 80% of RAM, per profile (prompt 03;
# 60% held for the platform alone in prompt 02).
# Each profile is checked against its reference RAM (profiles/<p>.env:
# HQ_BUDGET_REF_RAM_MB) three ways (prompt 05.1 §2.10):
#   - the profile itself fits, with at least HEADROOM_PERCENT of the budget free;
#   - the profile plus each opt-in profile (e.g. cadvisor, stt) still fits:
#     enforced when that opt-in profile is switched on here (HQ_<NAME>=on),
#     else an over-budget combination is printed but does not fail (hq.sh
#     refuses to switch it on while it is over; prompt 06 §3);
# and on the server the active profile is also checked against the real MemTotal.
# tmpfs mounts are charged to their container's memory, so they live inside
# its limit (they are not added on top).
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
ensure_env

PERCENT=80
HEADROOM_PERCENT=5
failed=0

limit_sum_mb() { # limit_sum_mb PROFILE [OPT_IN_PROFILE...]
  compose_json "$@" | jq '[.services[].deploy.resources.limits.memory | tonumber] | add / 1048576 | floor'
}

check() { # check LABEL SUM_MB RAM_MB WHERE [HEADROOM_PERCENT [ENFORCED]]
  local label="$1" sum="$2" ram="$3" where="$4" headroom="${5:-0}" enforced="${6:-yes}"
  local budget limit
  budget=$((ram * PERCENT / 100))
  limit=$((budget * (100 - headroom) / 100))
  local rule="${PERCENT}% of $ram MiB $where"
  if ((headroom)); then rule+=", ${headroom}% of it kept free"; fi
  if ((sum <= limit)); then
    echo "memory-budget: $label ok ($sum MiB <= $limit MiB; $rule)"
  elif [[ "$enforced" == no ]]; then
    # An opt-in profile that is off here: shown, never hidden, but not a failure;
    # hq.sh refuses to switch it on while it is over (prompt 06 §3).
    echo "memory-budget: $label OVER by $((sum - limit)) MiB ($sum MiB > $limit MiB; $rule;" \
      "not enabled; turning it on is the owner's decision: docs/ops/RUNBOOK.md, STT)"
  else
    echo "memory-budget: $label OVER ($sum MiB > $limit MiB; $rule)" >&2
    failed=1
  fi
}

# The full profile runs on any server from hq.sh's threshold up, so its budget
# reference is that threshold (prompt 05.1 §3), never one server's MemTotal.
threshold="$(sed -n 's/^FULL_PROFILE_MIN_MB=//p' "$HQ")"
full_ref="$(sed -n 's/^HQ_BUDGET_REF_RAM_MB=//p' "$REPO_DIR/infra/compose/profiles/full.env")"
if [[ "$full_ref" != "$threshold" ]]; then
  echo "memory-budget: full.env HQ_BUDGET_REF_RAM_MB=$full_ref, but hq.sh picks full from $threshold MiB" >&2
  failed=1
fi

mapfile -t OPT_IN < <(opt_in_profiles)
for profile in "${PROFILES[@]}"; do
  ref="$(sed -n 's/^HQ_BUDGET_REF_RAM_MB=//p' "$REPO_DIR/infra/compose/profiles/$profile.env")"
  check "$profile" "$(limit_sum_mb "$profile")" "$ref" "reference" "$HEADROOM_PERCENT"
  for extra in "${OPT_IN[@]}"; do
    enforced=no
    if opt_in_enabled "$extra"; then enforced=yes; fi
    check "$profile+$extra" "$(limit_sum_mb "$profile" "$extra")" "$ref" "reference" 0 "$enforced"
  done
done

if [[ -z "${CI:-}" && -r /proc/meminfo ]]; then
  active="$("$HQ" --print-profile)"
  enabled=()
  for extra in "${OPT_IN[@]}"; do
    if opt_in_enabled "$extra"; then enabled+=("$extra"); fi
  done
  label="$active"
  for extra in "${enabled[@]}"; do label+="+$extra"; done
  check "$label" "$(limit_sum_mb "$active" "${enabled[@]}")" \
    "$(awk '/^MemTotal:/ {print int($2 / 1024)}' /proc/meminfo)" "this server"
fi
exit "$failed"

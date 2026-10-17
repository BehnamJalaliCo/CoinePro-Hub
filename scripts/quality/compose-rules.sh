#!/usr/bin/env bash
# House rules for every service (see the header of infra/compose/compose.yaml):
# pinned image (no :latest), memory limit, and for long-running services
# restart unless-stopped + a healthcheck. One-shot jobs are listed below.
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
ensure_env

JOBS='["hq-tools","temporal-schema","temporal-namespace","db-provision","llm-migrate","api-migrate"]'
failed=0
for profile in "${PROFILES[@]}"; do
  problems="$(jq -r --argjson jobs "$JOBS" '
    .services | to_entries[] | .key as $svc | .value as $s
    | (if ($s.image | test(":[^/]+$") | not) or ($s.image | test(":latest$")) then "\($svc): image not pinned (\($s.image))" else empty end),
      (if ($s.deploy.resources.limits.memory // null) == null then "\($svc): no memory limit" else empty end),
      (if ($jobs | index($svc)) == null then
         (if $s.restart != "unless-stopped" then "\($svc): restart is \($s.restart // "unset")" else empty end),
         (if ($s.healthcheck.test // null) == null then "\($svc): no healthcheck" else empty end)
       else empty end)' <<<"$(compose_json "$profile")")"
  if [[ -n "$problems" ]]; then
    printf 'compose-rules: %s: %s\n' "$profile" "$problems" >&2
    failed=1
  else
    echo "compose-rules: $profile ok"
  fi
done
exit "$failed"

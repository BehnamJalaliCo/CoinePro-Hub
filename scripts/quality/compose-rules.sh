#!/usr/bin/env bash
# House rules for every service (see the header of infra/compose/compose.yaml):
# pinned image (no :latest), memory limit, and for long-running services
# restart unless-stopped + a healthcheck. One-shot jobs are listed below.
# Our own services also run as an explicit non-root user, on a read-only root
# filesystem, with every capability dropped. Network isolation (prompt 04.1):
# Temporal and OPA are never on hq-internal, and only the allow-list below
# may join hq-core.
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
ensure_env

JOBS='["hq-tools","temporal-schema","temporal-namespace","db-provision","llm-migrate","api-migrate"]'
HARDENED='["api","worker","opa","llm-router","claude-runtime","llm-migrate","api-migrate"]'
CORE_ONLY='["temporal","opa"]'
CORE_MEMBERS='["temporal","temporal-namespace","temporal-ui","opa","api","worker","postgres","prometheus"]'
failed=0
for profile in "${PROFILES[@]}"; do
  problems="$(jq -r --argjson jobs "$JOBS" --argjson hardened "$HARDENED" \
    --argjson core_only "$CORE_ONLY" --argjson core_members "$CORE_MEMBERS" '
    .services | to_entries[] | .key as $svc | .value as $s
    | (($s.networks // {}) | keys) as $nets
    | (if ($s.image | test(":[^/]+$") | not) or ($s.image | test(":latest$")) then "\($svc): image not pinned (\($s.image))" else empty end),
      (if ($s.deploy.resources.limits.memory // null) == null then "\($svc): no memory limit" else empty end),
      (if ($jobs | index($svc)) == null then
         (if $s.restart != "unless-stopped" then "\($svc): restart is \($s.restart // "unset")" else empty end),
         (if ($s.healthcheck.test // null) == null then "\($svc): no healthcheck" else empty end)
       else empty end),
      (if ($hardened | index($svc)) != null then
         (if (($s.user // "") | test("^[1-9][0-9]*(:[0-9]+)?$")) | not then "\($svc): no explicit non-root user" else empty end),
         (if $s.read_only != true then "\($svc): root filesystem not read-only" else empty end),
         (if (($s.cap_drop // []) | index("ALL")) == null then "\($svc): capabilities not dropped" else empty end)
       else empty end),
      (if ($core_only | index($svc)) != null and ($nets | index("hq-internal")) != null
       then "\($svc): must not be on hq-internal" else empty end),
      (if ($nets | index("hq-core")) != null and ($core_members | index($svc)) == null
       then "\($svc): not allowed on hq-core" else empty end)' <<<"$(compose_json "$profile")")"
  if [[ -n "$problems" ]]; then
    printf 'compose-rules: %s: %s\n' "$profile" "$problems" >&2
    failed=1
  else
    echo "compose-rules: $profile ok"
  fi
done
exit "$failed"

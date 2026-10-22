#!/usr/bin/env bash
# House rules for every service (see the header of infra/compose/compose.yaml):
# pinned image (no :latest), memory limit, and for long-running services
# restart unless-stopped + a healthcheck. One-shot jobs are listed below.
# Our own services also run as an explicit non-root user, on a read-only root
# filesystem, with every capability dropped.
# Network isolation (prompt 04.1, 05.1 §2.9): Temporal, OPA, the Tool Gateway
# and the web panel are never on hq-internal; some services sit on exactly one
# network; only an allow-list may join hq-core, hq-agent and hq-edge; and
# hq-agent and hq-edge have no route out of the host (internal).
# Prompt 07 §2: egress is the agents' only route out (hq-egress, with SearXNG);
# the gateway reaches it on hq-egress-api, the browser on hq-browser (both
# internal); none of the three is on any other network. Prompt 10 §4.2: the
# worker joins hq-egress-api for the support desk's sends (POST /v1/support/send).
# Prompt 09 §4: the provisioner sits on hq-prov (api, OpenBao) and hq-prov-out
# (egress) only; both internal.
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
ensure_env

JOBS='["hq-tools","temporal-schema","temporal-namespace","db-provision","llm-migrate","api-migrate","stt-fetch",
  "backup-tools","tts"]'
HARDENED='["api","worker","opa","llm-router","claude-runtime","llm-migrate","api-migrate","gateway","web","stt","stt-fetch",
  "backup-tools","egress","searxng","browser","provisioner","tts"]'
NOT_INTERNAL='["temporal","opa","gateway","web","stt","egress","searxng","browser","provisioner","tts"]'
# Services whose networks are exactly these.
ONLY_ON='{"gateway":["hq-agent","hq-egress-api"],"opa":["hq-agent"],"web":["hq-edge"],"claude-runtime":["hq-llm"],
  "stt":["hq-stt"],"stt-fetch":["hq-fetch"],
  "egress":["hq-browser","hq-egress","hq-egress-api","hq-prov-out"],"searxng":["hq-egress"],"browser":["hq-browser"],
  "provisioner":["hq-prov","hq-prov-out"],"tts":["hq-tts"]}'
# Allow-list of every restricted network.
MEMBERS='{
  "hq-core":["temporal","temporal-namespace","temporal-ui","api","worker","postgres","prometheus"],
  "hq-agent":["worker","gateway","api","opa"],
  "hq-edge":["caddy","web"],
  "hq-stt":["worker","stt"],
  "hq-fetch":["stt-fetch"],
  "hq-egress":["egress","searxng"],
  "hq-egress-api":["gateway","egress","worker"],
  "hq-browser":["egress","browser"],
  "hq-prov":["provisioner","api","openbao"],
  "hq-prov-out":["provisioner","egress"],
  "hq-tts":["tts","api","openbao"]}'
INTERNAL_NETS='["hq-agent","hq-edge","hq-stt","hq-egress-api","hq-browser","hq-prov","hq-prov-out","hq-tts"]'
# The opt-in profiles' services (cadvisor, stt) follow the same rules.
mapfile -t OPT_IN < <(opt_in_profiles)
failed=0
# Prompt 7.1 §2.20: Chromium's sandbox is on, with Playwright's own seccomp
# profile (pinned by hash) and no capability but SYS_CHROOT in the bounding set.
SECCOMP="$REPO_DIR/infra/browser/seccomp_profile.json"
SECCOMP_SHA256="cc3e61cabda6bbc1e53e54d27ba4d55a9d3be829b6dd1a596f4a7b31b1cc7849"
if [[ "$(sha256sum "$SECCOMP" 2>/dev/null | cut -d' ' -f1)" != "$SECCOMP_SHA256" ]]; then
  echo "compose-rules: infra/browser/seccomp_profile.json is not Playwright's v1.63.0 profile" >&2
  failed=1
fi
for profile in "${PROFILES[@]}"; do
  problems="$(jq -r '.services.browser as $b
    | (if (($b.security_opt // []) | index("seccomp=../browser/seccomp_profile.json")) == null
       then "browser: not on the pinned seccomp profile" else empty end),
      (if (($b.security_opt // []) | index("no-new-privileges:true")) == null
       then "browser: no-new-privileges is off" else empty end),
      (if ($b.cap_add // []) != ["SYS_CHROOT"] then "browser: cap_add must be exactly [SYS_CHROOT]" else empty end),
      (if ($b.environment.BROWSER_SANDBOX // "") != "1" then "browser: BROWSER_SANDBOX is not 1" else empty end)
    ' <<<"$(compose_json "$profile")")"
  if [[ -n "$problems" ]]; then
    printf 'compose-rules: %s: %s\n' "$profile" "$problems" >&2
    failed=1
  fi
done
for profile in "${PROFILES[@]}"; do
  problems="$(jq -r --argjson jobs "$JOBS" --argjson hardened "$HARDENED" \
    --argjson not_internal "$NOT_INTERNAL" --argjson only_on "$ONLY_ON" \
    --argjson members "$MEMBERS" --argjson internal_nets "$INTERNAL_NETS" '
    (.networks // {}) as $declared
    | ($internal_nets[] | . as $n
       | if ($declared[$n] // null) == null then "network \($n): not declared"
         elif $declared[$n].internal != true then "network \($n): not internal" else empty end),
      (.services | to_entries[] | .key as $svc | .value as $s
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
      (if ($not_internal | index($svc)) != null and ($nets | index("hq-internal")) != null
       then "\($svc): must not be on hq-internal" else empty end),
      (if ($only_on[$svc] // null) != null and ($nets != ($only_on[$svc] | sort))
       then "\($svc): networks are \($nets | join(",")), must be exactly \($only_on[$svc] | join(","))" else empty end),
      ($members | to_entries[] | .key as $net
       | if ($nets | index($net)) != null and (.value | index($svc)) == null
         then "\($svc): not allowed on \($net)" else empty end))' <<<"$(compose_json "$profile" "${OPT_IN[@]}")")"
  if [[ -n "$problems" ]]; then
    printf 'compose-rules: %s: %s\n' "$profile" "$problems" >&2
    failed=1
  else
    echo "compose-rules: $profile ok"
  fi
done
exit "$failed"

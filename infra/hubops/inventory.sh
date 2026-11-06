#!/usr/bin/env bash
# The host's half of the §25.2 connection table for hub.ops `inventory` (contract §38.1), as one
# JSON line; the api adds the hub's own rows (players and sign-ins, the voice key yes/no, growth
# connections, runners, backups) and stores the whole table. Names and states only: no value of
# any secret is read (a key's presence is the hub's own record of it, never OpenBao's value).
#   switches  each optional service's switch (snapshot.sh)
#   services  running / not running / unhealthy, by name (the long-running ones)
#   n8n       off | up | down, and its workflows (count, active) when it is up
#   memory    total, budget, caps, free (snapshot.sh)
set -euo pipefail
umask 077

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$HERE/../.." && pwd)"
HQ="${HQ_SH:-$REPO_DIR/infra/compose/hq.sh}"
BIN="${HQ_HUBOPS_BIN:-$HERE}"

snap="$("$BIN/snapshot.sh" 2>/dev/null)" || snap='{}'
jq -e 'type == "object"' <<<"$snap" >/dev/null 2>&1 || snap='{}'

n8n='{"health": "off"}'
if [[ "$(jq -r '.switches.automations // "off"' <<<"$snap")" == on ]]; then
  if "$HQ" --profile automations exec -T n8n wget -q -O /dev/null http://127.0.0.1:5678/healthz \
    >/dev/null 2>&1; then
    wf="$("$BIN/n8n.sh" list 2>/dev/null)" || wf='null'
    jq -e 'type == "array"' <<<"$wf" >/dev/null 2>&1 || wf='null'
    n8n="$(jq -cn --argjson wf "$wf" \
      '{health: "up", workflows: ($wf | if . == null then null else length end),
        active: ($wf | if . == null then null else map(select(.active)) | length end)}')"
  else
    n8n='{"health": "down"}'
  fi
fi

jq -cn --argjson snap "$snap" --argjson n8n "$n8n" '
  ($snap.services // [] | map(select((.one_shot | not) and (.state != "absent")))) as $long
  | {switches: ($snap.switches // {}),
     services: {running: [$long[] | select(.state == "running") | .service],
                not_running: [$long[] | select(.state != "running") | .service],
                unhealthy: [$long[] | select(.health == "unhealthy") | .service]},
     n8n: $n8n,
     memory: ($snap.memory // null)}'

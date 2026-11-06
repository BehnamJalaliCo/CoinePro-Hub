#!/usr/bin/env bash
# n8n for hub.ops (contract §38.1), through n8n's own CLI inside its container and, for the
# executions, a read-only query of n8n's database. Run by the hub-ops dispatcher as user Hub.
#   n8n.sh list                       the workflows: [{id, name, active}]
#   n8n.sh executions LIMIT [ID]      the latest executions (state and time only), LIMIT <= 50
#   n8n.sh activate ID on|off         publish / unpublish one workflow (n8n 2.x; 1.x: update
#                                     --active), then n8n restarts so its webhooks listen
#   n8n.sh create FILE                import one workflow (the owner sealed it) inactive, with a
#                                     fresh id: never over an existing one
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HQ="${HQ_SH:-$REPO_DIR/infra/compose/hq.sh}"
n8n() { "$HQ" --profile automations exec -T n8n n8n "$@"; }
ID_RE='^[A-Za-z0-9]{1,40}$'

workflows() { # id|name lines -> [{id, name}]
  jq -Rn '[inputs | select(test("^[A-Za-z0-9]{1,40}\\|")) | capture("^(?<id>[A-Za-z0-9]+)\\|(?<name>.*)$")]'
}

case "${1:-}" in
  list)
    all="$(n8n list:workflow 2>/dev/null | workflows)"
    on="$(n8n list:workflow --active=true 2>/dev/null | workflows)"
    jq -cn --argjson all "$all" --argjson on "$on" \
      '($on | map(.id)) as $ids | $all | map(. + {active: (.id as $i | $ids | index($i) != null)})'
    ;;
  executions)
    limit="${2:-}" wf="${3:-}"
    if ! [[ "$limit" =~ ^[0-9]{1,2}$ ]] || ((limit < 1 || limit > 50)); then
      echo "n8n: limit 1..50" >&2
      exit 2
    fi
    [[ -z "$wf" || "$wf" =~ $ID_RE ]] || { echo "n8n: a workflow id" >&2; exit 2; }
    # Read only (the session refuses any write); the values go in as psql variables.
    printf '%s\n' "SELECT coalesce(json_agg(x), '[]') FROM (
        SELECT e.id, e.\"workflowId\" AS workflow, w.name, e.status, e.mode,
               e.\"startedAt\" AS started_at, e.\"stoppedAt\" AS stopped_at
        FROM execution_entity e LEFT JOIN workflow_entity w ON w.id = e.\"workflowId\"
        WHERE (:'wf' = '' OR e.\"workflowId\" = :'wf')
        ORDER BY e.id DESC LIMIT :lim) x;" |
      "$HQ" exec -T -e PGOPTIONS='-c default_transaction_read_only=on' postgres \
        psql -U postgres -d n8n -X -At -v ON_ERROR_STOP=1 -v lim="$limit" -v wf="$wf" -f -
    ;;
  activate)
    id="${2:-}" want="${3:-}"
    [[ "$id" =~ $ID_RE ]] || { echo "n8n: a workflow id" >&2; exit 2; }
    case "$want" in
      on) n8n publish:workflow --id="$id" || n8n update:workflow --id="$id" --active=true ;;
      off) n8n unpublish:workflow --id="$id" || n8n update:workflow --id="$id" --active=false ;;
      *) echo "n8n: on or off" >&2; exit 2 ;;
    esac
    "$HQ" --profile automations restart n8n >/dev/null # webhooks register when n8n starts
    echo "n8n: $id $want"
    ;;
  create)
    file="${2:-}"
    [[ -f "$file" ]] || { echo "n8n: no workflow file" >&2; exit 2; }
    id="$(openssl rand -hex 8)"
    jq --arg id "$id" 'if type == "object" and (.nodes | type == "array") then . + {id: $id, active: false}
                       else error("not a workflow") end' "$file" >"$file.new"
    # Into the container's own tmpfs through stdin, imported, removed.
    "$HQ" --profile automations exec -T n8n sh -c 'umask 077; cat >/tmp/hubops-workflow.json' <"$file.new"
    rc=0
    n8n import:workflow --input=/tmp/hubops-workflow.json || rc=$?
    "$HQ" --profile automations exec -T n8n rm -f /tmp/hubops-workflow.json || true
    rm -f "$file.new"
    ((rc == 0)) || exit "$rc"
    echo "n8n: imported inactive as $id (activate it with n8n.activate)"
    ;;
  *)
    echo "usage: n8n.sh list | executions LIMIT [ID] | activate ID on|off | create FILE" >&2
    exit 2
    ;;
esac

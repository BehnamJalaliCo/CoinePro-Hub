#!/usr/bin/env bash
# The hub-ops dispatcher (contract §38.1, §38.3), run every 10 s by coinepro-hq-hubops.timer as user
# Hub. One job at a time (flock): claim it from the api, check it against this file's OWN allow-list,
# run exactly that command (an argv, never a shell, never eval), mask its output and post `done`.
# Between jobs, at most every 60 s, it posts the host's snapshot (snapshot.sh) for the owner's
# «سرویس‌ها» page.
#
# - Exits at once without its own api token ($HQ_SECRETS_DIR/hubops/api-auth; make hubops-token).
# - The api hands out no job while the holding's kill switch is engaged.
# - Defence in depth: the api built the argv from validated arguments (apps/api domain/hub_ops.py);
#   this dispatcher builds the same argv again from the op and its arguments with its own case
#   table below and runs it only when both are equal. An op, a service or an argument outside the
#   table, or any of ; & | $ ` < > or a newline in an argument, is refused and nothing runs.
# - The api has no published port: every call goes through a short-lived curl container on
#   hq-internal, its token in a header file (600) mounted read-only, never on a command line.
# - The output is masked here (mask.sh), capped at 64 KB, and masked again by the api.
#
# Usage: dispatch.sh   (the timer runs it; tests set HQ_SH, HQ_HUBOPS_CURL, HQ_HUBOPS_BIN, HQ_MAKE)
set -euo pipefail
umask 077

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$HERE/../.." && pwd)"
HQ="${HQ_SH:-$REPO_DIR/infra/compose/hq.sh}"
BIN="${HQ_HUBOPS_BIN:-$HERE}" # inventory.sh, n8n.sh, profile.sh, snapshot.sh
MAKE_BIN="${HQ_MAKE:-make}"
SECRETS_DIR="${HQ_SECRETS_DIR:-/home/Hub/.secrets}"
AUTH_FILE="$SECRETS_DIR/hubops/api-auth" # "Authorization: Bearer ..." (600)
CURL_IMAGE="curlimages/curl:8.17.0"
API_NET="${HQ_HUBOPS_API_NET:-hq-internal}"
API_URL="${HQ_HUBOPS_API_URL:-http://api:8000}"
WORK_ROOT="${RUNTIME_DIRECTORY:-${XDG_RUNTIME_DIR:-/tmp}}"
STATE_DIR="${STATE_DIRECTORY:-$WORK_ROOT}"
SNAPSHOT_EVERY_S="${HQ_HUBOPS_SNAPSHOT_S:-60}"
DONE_TRIES="${HQ_HUBOPS_DONE_TRIES:-36}" # the api may be restarting (restart api, a profile): 3 min
DONE_SLEEP_S="${HQ_HUBOPS_DONE_SLEEP_S:-5}"
OUTPUT_MAX=65536

# The dispatcher's own allow-list (kept equal to apps/api domain/hub_ops.py by its tests).
SERVICES=" hq-tools backup-tools postgres valkey nats temporal-schema temporal temporal-namespace
  temporal-ui openbao db-provision llm-migrate llm-router claude-runtime api-migrate opa api worker
  gateway egress searxng browser web caddy prometheus loki alloy n8n grafana node-exporter tempo
  otel-collector stt-fetch ocr-fetch provisioner stt ocr substitute-runner browser-web
  browser-web-login web-login-relay tts media-courier media-render newsletter-provision listmonk
  cadvisor mcp-time mcp-codecortex mcp-codecortex-index "
RESTARTABLE=" llm-router claude-runtime opa api worker gateway egress searxng browser web prometheus
  loki alloy n8n grafana node-exporter tempo otel-collector provisioner ocr browser-web listmonk
  cadvisor temporal-ui mcp-time mcp-codecortex "
PROFILES=" media tts stt ocr newsletter automations tracing " # mcp is never switched from here
PS_FORMAT=$'table {{.Service}}\t{{.State}}\t{{.Health}}\t{{.Status}}'

if [[ "${1:-}" == --print-lists ]]; then # the tests keep these equal to the api's catalogue
  for k in SERVICES RESTARTABLE PROFILES; do
    read -ra words <<<"$(tr '\n' ' ' <<<"${!k}")"
    printf '%s:%s\n' "$(tr '[:upper:]' '[:lower:]' <<<"$k")" "${words[*]}"
  done
  exit 0
fi
if [[ ! -r "$AUTH_FILE" ]]; then
  echo "hubops: no dispatcher token yet ($AUTH_FILE; make hubops-token)" >&2
  exit 0
fi
exec 9>"$WORK_ROOT/hubops.lock"
flock -n 9 || exit 0 # one job at a time

work="$(mktemp -d "$WORK_ROOT/hubjob.XXXXXX")"
trap 'rm -rf "$work"' EXIT

api() { # api PATH: POST stdin to the api's internal route, the answer on stdout; non-zero on failure
  if [[ -n "${HQ_HUBOPS_CURL:-}" ]]; then # tests: a fake api
    "$HQ_HUBOPS_CURL" "$1"
    return
  fi
  # No log driver: the claim and the output reach only the attached stdout,
  # never a json-file log that Alloy ships to Loki.
  docker run --rm -i --init --log-driver none --network "$API_NET" --read-only --cap-drop ALL \
    --security-opt no-new-privileges:true --user "$(id -u):$(id -g)" --memory 32m \
    -v "$AUTH_FILE:/run/auth:ro" --entrypoint timeout "$CURL_IMAGE" \
    45 curl -sS -f -m 30 -X POST -H @/run/auth -H 'Content-Type: application/json' \
    --data-binary @- "$API_URL$1"
}

snapshot_due() {
  [[ ! -e "$STATE_DIR/snapshot.at" ]] ||
    (($(date +%s) - $(stat -c %Y "$STATE_DIR/snapshot.at") >= SNAPSHOT_EVERY_S))
}

post_snapshot() { # never fails the run: the page shows the last one with its time
  if "$BIN/snapshot.sh" >"$work/snapshot.json" 2>/dev/null && jq -e 'type == "object"' "$work/snapshot.json" >/dev/null 2>&1; then
    api /internal/v1/hubops/snapshot <"$work/snapshot.json" >/dev/null 2>&1 || true
  fi
  touch "$STATE_DIR/snapshot.at" 2>/dev/null || true
}

post_done() { # post_done BODY_FILE: retried while the api restarts
  local i
  for ((i = 1; i <= DONE_TRIES; i++)); do
    if api "/internal/v1/hubops/$ref/done" <"$1" >/dev/null 2>&1; then return 0; fi
    sleep "$DONE_SLEEP_S"
  done
  echo "hubops: $ref: the api did not take the answer" >&2
  return 1
}

refuse() { # refuse REASON: nothing ran
  echo "hubops: $ref refused by the dispatcher's allow-list: $1" >&2
  jq -n --arg r "$1" '{exit_code: -1, output: ("refused by the hub-ops dispatcher: " + $r), refused: "not_allowed"}' \
    >"$work/done.json"
  post_done "$work/done.json" || true
  post_snapshot
  exit 0
}

# in_list NAME LIST: NAME is one word of LIST. The lists span lines, so any whitespace separates;
# an empty name, or one with a space, never matches (two words or an indent would).
in_list() { [[ "$1" =~ ^[a-z0-9-]+$ && " ${2//[[:space:]]/ } " == *" $1 "* ]]; }

claim="$(printf '' | api /internal/v1/hubops/claim 2>/dev/null)" || claim='{}'
ref="$(jq -r '.job.ref // empty' <<<"$claim" 2>/dev/null || true)"
if [[ ! "$ref" =~ ^HJ-[0-9]{6,}$ ]]; then # nothing to do (or the holding is locked)
  if snapshot_due; then post_snapshot; fi
  exit 0
fi

op="$(jq -r '.job.op // ""' <<<"$claim")"
timeout_s="$(jq -r '.job.timeout_s // 300' <<<"$claim")"
[[ "$timeout_s" =~ ^[0-9]{2,4}$ ]] || refuse "timeout"
# Every string argument (but a workflow's JSON, which never reaches a command line) is plain.
if jq -e '[.job.args // {} | del(.workflow_json) | .. | strings | select(test("[;&|$`<>\n\r]"))] | length > 0' \
  <<<"$claim" >/dev/null; then
  refuse "a forbidden character in an argument"
fi
arg() { jq -r --arg k "$1" '.job.args // {} | if has($k) and .[$k] != null then .[$k] | tostring else empty end' <<<"$claim"; }

# ---------------------------------------------------- the dispatcher's own table --
declare -a want
case "$op" in
  status) want=(infra/compose/hq.sh ps --all --format "$PS_FORMAT") ;;
  logs)
    service="$(arg service)" lines="$(arg lines)" since="$(arg since)"
    in_list "$service" "$SERVICES" || refuse "not a service of the stack"
    if ! [[ "$lines" =~ ^[0-9]{1,3}$ ]] || ((lines < 1 || lines > 500)); then refuse "lines"; fi
    want=(infra/compose/hq.sh logs --no-color --tail "$lines")
    if [[ -n "$since" ]]; then
      [[ "$since" =~ ^[0-9]{1,4}[smh]$ ]] || refuse "since"
      want+=(--since "$since")
    fi
    want+=("$service")
    ;;
  stats) want=(infra/hubops/snapshot.sh) ;;
  verify) want=(make verify-live) ;;
  inventory) want=(infra/hubops/inventory.sh) ;;
  n8n.list) want=(infra/hubops/n8n.sh list) ;;
  n8n.executions)
    limit="$(arg limit)" wf="$(arg workflow)"
    if ! [[ "$limit" =~ ^[0-9]{1,2}$ ]] || ((limit < 1 || limit > 50)); then refuse "limit"; fi
    want=(infra/hubops/n8n.sh executions "$limit")
    if [[ -n "$wf" ]]; then
      [[ "$wf" =~ ^[A-Za-z0-9]{1,40}$ ]] || refuse "workflow"
      want+=("$wf")
    fi
    ;;
  restart)
    service="$(arg service)"
    in_list "$service" "$RESTARTABLE" || refuse "not a service that is restarted from here"
    want=(infra/compose/hq.sh restart "$service")
    ;;
  profile)
    name="$(arg name)" on="$(arg on)"
    in_list "$name" "$PROFILES" || refuse "not an optional service"
    [[ "$on" == true || "$on" == false ]] || refuse "on"
    want=(infra/hubops/profile.sh "$name" "$([[ "$on" == true ]] && echo on || echo off)")
    while IFS= read -r k; do
      [[ -z "$k" ]] && continue
      in_list "$k" "$PROFILES" && [[ "$k" != "$name" ]] || refuse "turn_off"
      want+=("$k")
    done < <(jq -r '.job.args.turn_off // [] | .[] | tostring' <<<"$claim")
    ;;
  n8n.import) want=(make n8n-import) ;;
  n8n.activate)
    wf="$(arg workflow)" on="$(arg on)"
    [[ "$wf" =~ ^[A-Za-z0-9]{1,40}$ ]] || refuse "workflow"
    [[ "$on" == true || "$on" == false ]] || refuse "on"
    want=(infra/hubops/n8n.sh activate "$wf" "$([[ "$on" == true ]] && echo on || echo off)")
    ;;
  backup) want=(make backup-hourly) ;;
  n8n.create)
    jq -e '.job.args.workflow_json | type == "object" and (.nodes | type == "array")' <<<"$claim" >/dev/null ||
      refuse "workflow_json"
    want=(infra/hubops/n8n.sh create @workflow_json)
    ;;
  *) refuse "unknown operation" ;;
esac

if [[ "$(jq -c ".job.argv" <<<"$claim")" != "$(printf "%s\n" "${want[@]}" | jq -cRn "[inputs]")" ]]; then
  refuse "the api's command is not the one this table builds"
fi

# ------------------------------------------------------------------- run it --
cmd=("${want[@]}")
case "${cmd[0]}" in
  infra/compose/hq.sh) cmd[0]="$HQ" ;;
  infra/hubops/*) cmd[0]="$BIN/${cmd[0]#infra/hubops/}" ;;
  make) cmd=("$MAKE_BIN" -C "$REPO_DIR" "${cmd[@]:1}") ;;
esac
if [[ "$op" == n8n.create ]]; then
  # The workflow goes in a file (never on a command line): named, inactive, without an id.
  jq '.job.args as $a | $a.workflow_json + {name: $a.name, active: false} | del(.id)' <<<"$claim" \
    >"$work/workflow.json"
  cmd[${#cmd[@]} - 1]="$work/workflow.json"
fi
ec=0
(cd "$REPO_DIR" && exec timeout --kill-after=30 "$timeout_s" "${cmd[@]}") </dev/null >"$work/out" 2>&1 || ec=$?
"$HERE/mask.sh" <"$work/out" | tail -c "$OUTPUT_MAX" >"$work/masked"
((ec <= 255)) || ec=255
jq -n --rawfile out "$work/masked" --argjson ec "$ec" '{exit_code: $ec, output: $out}' >"$work/done.json"
post_done "$work/done.json" || true
post_snapshot

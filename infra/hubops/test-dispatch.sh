#!/usr/bin/env bash
# Tests of infra/hubops/dispatch.sh, profile.sh and mask.sh (contract §38) with a fake api, a fake
# hq.sh and a fake make (no docker, no network): nothing without its token, nothing while the
# holding is locked, a job's done relayed and masked, and the allow-list: an op, a service or an
# argument outside the dispatcher's own table, a command that is not the one the table builds, or
# ; && $( in an argument is refused and nothing runs. The allow-list equals the api's catalogue.
# Run by `make hubops-test` (and scripts/quality/infra.sh when it lists it).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
failed=0
ok() { echo "test-hubops: ok: $1"; }
bad() { echo "test-hubops: FAIL: $1" >&2; failed=1; }

mkdir -p "$T/secrets/hubops" "$T/run" "$T/state" "$T/bin"
printf 'Authorization: Bearer fake\n' >"$T/secrets/hubops/api-auth"
PS_FORMAT=$'table {{.Service}}\t{{.State}}\t{{.Health}}\t{{.Status}}'

cat >"$T/fake-api" <<'EOF'
#!/usr/bin/env bash
body="$(cat)"
printf '%s\t%s\n' "$1" "$(printf '%s' "$body" | tr '\n' ' ')" >>"$FAKE_DIR/api.log"
case "$1" in
  */hubops/claim) cat "$FAKE_DIR/claim.json" ;;
  *) echo '{"ok": true}' ;;
esac
EOF
cat >"$T/fake-hq" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"$FAKE_DIR/argv.log"
case " $* " in
  *" config --quiet "*)
    # FAKE_OVER=1: media never fits; FAKE_OVER=ocr: media fits only with ocr counted off.
    if [[ "${HQ_MEDIA:-}" == on ]] &&
      [[ "${FAKE_OVER:-0}" == 1 || ("${FAKE_OVER:-0}" == ocr && "${HQ_OCR:-}" != off) ]]; then
      echo "warning: HQ_MEDIA=on ignored (the full profile plus media needs 12668 MiB, 182 MiB over the budget)" >&2
    fi ;;
  *" ps "*) printf 'api\trunning\thealthy\tUp 3 hours\nAPI_TOKEN=s3cr3t-value-123 Bearer abcdefgh12345678\n' ;;
  *" logs "*) echo "log line DB_PASSWORD=hunter2" ;;
esac
EOF
cat >"$T/fake-make" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"$FAKE_DIR/make.log"
exit "${FAKE_MAKE_RC:-0}"
EOF
cat >"$T/fake-set-env" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"$FAKE_DIR/set-env.log"
EOF
for f in profile.sh n8n.sh inventory.sh; do
  cat >"$T/bin/$f" <<EOF
#!/usr/bin/env bash
printf '%s %s\n' "$f" "\$*" >>"\$FAKE_DIR/bin.log"
if [[ "$f" == n8n.sh && "\${1:-}" == create ]]; then cp "\$2" "\$FAKE_DIR/workflow.json"; fi
EOF
done
printf '#!/usr/bin/env bash\necho %s\n' "'{\"memory\": {\"total_mb\": 15608}}'" >"$T/bin/snapshot.sh"
chmod +x "$T/fake-api" "$T/fake-hq" "$T/fake-make" "$T/fake-set-env" "$T"/bin/*.sh

run() { # run CLAIM_JSON
  rm -f "$T"/api.log "$T"/argv.log "$T"/make.log "$T"/bin.log "$T"/workflow.json "$T/state/snapshot.at"
  printf '%s' "$1" >"$T/claim.json"
  FAKE_DIR="$T" HQ_SH="$T/fake-hq" HQ_HUBOPS_CURL="$T/fake-api" HQ_HUBOPS_BIN="$T/bin" \
    HQ_MAKE="$T/fake-make" HQ_SECRETS_DIR="$T/secrets" RUNTIME_DIRECTORY="$T/run" \
    STATE_DIRECTORY="$T/state" HQ_HUBOPS_DONE_SLEEP_S=0 bash "$HERE/dispatch.sh"
}
job() { # job OP ARGS_JSON ARGV...
  local op="$1" args="$2"
  shift 2
  printf '%s\n' "$@" | jq -cRn --arg op "$op" --argjson args "$args" '{job: {ref: "HJ-000042",
    op: $op, args: $args, argv: [inputs], timeout_s: 60}}'
}
done_body() { grep -F "/hubops/HJ-000042/done" "$T/api.log" | cut -f2-; }
ran() { [[ -s "$T/argv.log" || -s "$T/make.log" || -s "$T/bin.log" ]]; }
refused() { # refused CLAIM WHAT
  run "$1"
  if ran; then
    bad "$2: something ran"
  elif [[ "$(done_body | jq -r .refused 2>/dev/null)" != not_allowed ]]; then
    bad "$2: no refusal was posted ($(done_body))"
  else
    ok "refused: $2"
  fi
}

# Without its token: nothing at all.
mv "$T/secrets/hubops/api-auth" "$T/auth.off"
run "$(job status '{}' infra/compose/hq.sh ps --all --format "$PS_FORMAT")"
if [[ -e "$T/api.log" ]] || ran; then bad "no token still called the api"; else ok "nothing without its token"; fi
mv "$T/auth.off" "$T/secrets/hubops/api-auth"

# The holding is locked: the api answers no job; only the snapshot goes up.
run '{"job": null, "skipped": "holding_locked"}'
if ran || grep -q "/done" "$T/api.log"; then
  bad "a locked holding still ran something"
elif ! grep -q "/hubops/snapshot" "$T/api.log"; then
  bad "no snapshot was posted while idle"
else
  ok "nothing runs while the holding is locked; the snapshot is posted"
fi

# status: the table's own command runs; the done is relayed and masked.
run "$(job status '{}' infra/compose/hq.sh ps --all --format "$PS_FORMAT")"
out="$(done_body | jq -r .output)"
if [[ "$(cat "$T/argv.log")" != "ps --all --format $PS_FORMAT" ]]; then
  bad "status did not run hq.sh ps ($(cat "$T/argv.log" 2>/dev/null))"
elif [[ "$(done_body | jq -r .exit_code)" != 0 ]] || [[ "$out" != *"api"*"running"* ]]; then
  bad "the done of status was not relayed ($(done_body))"
elif [[ "$out" == *s3cr3t-value-123* || "$out" == *abcdefgh12345678* ]]; then
  bad "a secret left the host unmasked"
else
  ok "status: run, relayed, masked"
fi

# logs with valid arguments.
run "$(job logs '{"service": "api", "lines": 50, "since": "30m"}' \
  infra/compose/hq.sh logs --no-color --tail 50 --since 30m api)"
if [[ "$(cat "$T/argv.log")" != "logs --no-color --tail 50 --since 30m api" ]]; then
  bad "logs did not run as built"
elif [[ "$(done_body | jq -r .output)" == *hunter2* ]]; then
  bad "a password in a log left the host"
else
  ok "logs: run as built, masked"
fi

# The allow-list.
refused "$(job status '{}' bash -c id)" "a command that is not the table's"
refused "$(job reboot '{}' sudo reboot)" "an unknown operation"
refused "$(job logs '{"service": "api;rm -rf /", "lines": 5}' infra/compose/hq.sh logs --no-color --tail 5 'api;rm -rf /')" "; in an argument"
refused "$(job logs '{"service": "api && id", "lines": 5}' infra/compose/hq.sh logs --no-color --tail 5 'api && id')" "&& in an argument"
# shellcheck disable=SC2016 # the $( is the argument under test, never expanded
refused "$(job logs '{"service": "$(id)", "lines": 5}' infra/compose/hq.sh logs --no-color --tail 5 '$(id)')" "\$( in an argument"
refused "$(job logs '{"service": "ufw", "lines": 5}' infra/compose/hq.sh logs --no-color --tail 5 ufw)" "a service outside the stack"
refused "$(job logs '{"service": "api", "lines": 5000}' infra/compose/hq.sh logs --no-color --tail 5000 api)" "lines over 500"
refused "$(job restart '{"service": "postgres"}' infra/compose/hq.sh restart postgres)" "restart postgres"
refused "$(job restart '{"service": "openbao"}' infra/compose/hq.sh restart openbao)" "restart openbao"
refused "$(job profile '{"name": "mcp", "on": true}' infra/hubops/profile.sh mcp on)" "mcp from here"
refused "$(job n8n.activate '{"workflow": "a/b", "on": true}' infra/hubops/n8n.sh activate a/b on)" "a workflow id with a slash"
refused "$(job restart '{"service": "worker"}' infra/compose/hq.sh restart api)" "argv for another service"

# restart, profile (with turn_off), n8n.import: the table's commands run.
run "$(job restart '{"service": "worker"}' infra/compose/hq.sh restart worker)"
if [[ "$(cat "$T/argv.log")" == "restart worker" ]]; then ok "restart worker runs"; else bad "restart worker did not run"; fi
# A name that ends a line of the multi-line lists is still in them (worker, prometheus, listmonk).
run "$(job restart '{"service": "prometheus"}' infra/compose/hq.sh restart prometheus)"
if [[ "$(cat "$T/argv.log")" == "restart prometheus" ]]; then ok "restart prometheus runs"; else bad "restart prometheus did not run"; fi
run "$(job logs '{"service": "worker", "lines": 50}' infra/compose/hq.sh logs --no-color --tail 50 worker)"
if [[ "$(cat "$T/argv.log")" == "logs --no-color --tail 50 worker" ]]; then ok "logs worker runs"; else bad "logs worker did not run"; fi
for k in services restartable; do # every listed name passes the dispatcher's own check
  for s in $(bash "$HERE/dispatch.sh" --print-lists | sed -n "s/^$k://p"); do
    if [[ "$k" == services ]]; then
      run "$(job logs "{\"service\": \"$s\", \"lines\": 5}" infra/compose/hq.sh logs --no-color --tail 5 "$s")"
      [[ "$(cat "$T/argv.log" 2>/dev/null)" == "logs --no-color --tail 5 $s" ]] || bad "logs $s was refused"
    else
      run "$(job restart "{\"service\": \"$s\"}" infra/compose/hq.sh restart "$s")"
      [[ "$(cat "$T/argv.log" 2>/dev/null)" == "restart $s" ]] || bad "restart $s was refused"
    fi
  done
done
ok "every listed service: logs and restart (restartable) run"
refused "$(job logs '{"service": "", "lines": 5}' infra/compose/hq.sh logs --no-color --tail 5 '')" "an empty service"
refused "$(job logs '{"service": "api worker", "lines": 5}' infra/compose/hq.sh logs --no-color --tail 5 'api worker')" "two services in one"
run "$(job profile '{"name": "media", "on": true, "turn_off": ["ocr", "tts"]}' infra/hubops/profile.sh media on ocr tts)"
if [[ "$(cat "$T/bin.log")" == "profile.sh media on ocr tts" ]]; then ok "profile runs"; else
  bad "profile did not run ($(cat "$T/bin.log" 2>/dev/null))"
fi
run "$(job n8n.import '{}' make n8n-import)"
if [[ "$(cat "$T/make.log")" == "-C $REPO n8n-import" ]]; then ok "n8n.import runs make"; else
  bad "n8n.import ($(cat "$T/make.log" 2>/dev/null))"
fi

# n8n.create: the workflow goes in a file, never on a command line; inactive, named, no id.
wf='{"name": "x", "workflow_json": {"id": "abc", "nodes": [{"type": "n8n-nodes-base.cron"}], "connections": {}}}'
run "$(job n8n.create "$wf" infra/hubops/n8n.sh create @workflow_json)"
if ! [[ -s "$T/workflow.json" ]]; then
  bad "n8n.create did not hand a file over"
elif grep -q "n8n-nodes-base" "$T/bin.log"; then
  bad "the workflow reached a command line"
elif [[ "$(jq -c '[.name, .active, has("id")]' "$T/workflow.json")" != '["x",false,false]' ]]; then
  bad "the workflow file is not named, inactive and without an id ($(cat "$T/workflow.json"))"
else
  ok "n8n.create: a file, inactive, without an id"
fi

# The dispatcher's lists equal the api's catalogue (apps/api domain/hub_ops.py).
lists="$(bash "$HERE/dispatch.sh" --print-lists)"
api_lists="$(python3 - "$REPO/apps/api/src/hq_api/domain/hub_ops.py" <<'EOF'
import ast, sys
tree = ast.parse(open(sys.argv[1]).read())
vals = {}
for node in tree.body:
    target = getattr(node, "target", None) or (node.targets[0] if isinstance(node, ast.Assign) else None)
    if isinstance(target, ast.Name) and target.id in ("SERVICES", "NEVER_RESTART", "ONE_SHOTS"):
        v = node.value
        if isinstance(v, ast.Call):
            v = v.args[0]
        vals[target.id] = [e.value for e in v.elts]
    if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "PROFILE_RE":
        vals["PROFILE_RE"] = node.value.value
s = vals["SERVICES"]
r = [x for x in s if x not in vals["NEVER_RESTART"] and x not in vals["ONE_SHOTS"]]
p = [x for x in vals["PROFILE_RE"].strip("^$()").split("|") if x != "mcp"]
print("services:" + " ".join(sorted(s)))
print("restartable:" + " ".join(sorted(r)))
print("profiles:" + " ".join(sorted(p)))
EOF
)"
mine="$(while IFS=: read -r k v; do printf '%s:%s\n' "$k" "$(tr ' ' '\n' <<<"$v" | sort | xargs)"; done <<<"$lists")"
if [[ "$mine" == "$api_lists" ]]; then ok "the dispatcher's lists equal the api's catalogue"; else
  bad "the dispatcher's lists differ from the api's: $(diff <(echo "$mine") <(echo "$api_lists") | tr '\n' ' ')"
fi

# ... and the stack's own services (infra/compose/compose.yaml and mcp.yaml).
stack="$(awk '/^services:/ {on = 1; next} /^[^ #]/ {on = 0} on && /^  [a-z0-9-]+:[[:space:]]*$/ {sub(/:.*/, ""); sub(/^  /, ""); print}' \
  "$REPO/infra/compose/compose.yaml" "$REPO/infra/compose/mcp.yaml" | sort | xargs)"
if [[ "services:$stack" == "$(grep '^services:' <<<"$mine")" ]]; then ok "the services are the compose stack's"; else
  bad "the services differ from the compose stack's: $stack"
fi

# profile.sh: over the memory budget nothing changes (exit 3); else the make target runs, sudo-free.
rm -f "$T/make.log" "$T/argv.log"
rc=0
FAKE_DIR="$T" FAKE_OVER=1 HQ_SH="$T/fake-hq" HQ_MAKE="$T/fake-make" HQ_SET_ENV="$T/fake-set-env" \
  bash "$HERE/profile.sh" media on >"$T/p.out" 2>&1 || rc=$?
if ((rc != 3)) || [[ -s "$T/make.log" ]] || ! grep -q "182 MiB over" "$T/p.out"; then
  bad "profile over the budget: rc=$rc, make ran: $(cat "$T/make.log" 2>/dev/null)"
else
  ok "profile over the budget: refused (3), nothing changed"
fi
# Refused with a turn_off: the budget is asked first, so ocr is not switched off either.
rm -f "$T/make.log"
rc=0
FAKE_DIR="$T" FAKE_OVER=1 HQ_SH="$T/fake-hq" HQ_MAKE="$T/fake-make" HQ_SET_ENV="$T/fake-set-env" \
  bash "$HERE/profile.sh" media on ocr >"$T/p.out" 2>&1 || rc=$?
if ((rc != 3)) || [[ -s "$T/make.log" ]]; then
  bad "profile refused with turn_off: rc=$rc, make ran: $(cat "$T/make.log" 2>/dev/null)"
else
  ok "profile refused with turn_off: nothing switched off"
fi
rm -f "$T/make.log"
FAKE_DIR="$T" FAKE_OVER=ocr HQ_SH="$T/fake-hq" HQ_MAKE="$T/fake-make" HQ_SET_ENV="$T/fake-set-env" \
  bash "$HERE/profile.sh" media on ocr >/dev/null 2>&1 || bad "profile media on failed"
if [[ "$(cat "$T/make.log")" != "-C $REPO ocr-off HQ_NO_SUDO=1"$'\n'"-C $REPO media-on HQ_NO_SUDO=1" ]]; then
  bad "profile did not turn ocr off first and then media on ($(cat "$T/make.log"))"
else
  ok "profile: turn_off first, then on, without sudo"
fi
rm -f "$T/make.log" "$T/set-env.log"
FAKE_DIR="$T" FAKE_MAKE_RC=2 HQ_SH="$T/fake-hq" HQ_MAKE="$T/fake-make" HQ_SET_ENV="$T/fake-set-env" \
  bash "$HERE/profile.sh" tts on >/dev/null 2>&1 && bad "a failed target answered success"
if [[ "$(cat "$T/set-env.log" 2>/dev/null)" == "HQ_TTS off" ]]; then ok "a failed target leaves the switch off"; else
  bad "a failed target left the switch on"
fi

# mask.sh by itself.
masked="$(printf '%s\n' 'X_SECRET=abc' '{"password": "p"}' 'https://u:pw@host/x' 'ghp_abcdefghijklmnopqrstuvwxyz0123456789' \
  '-----BEGIN RSA PRIVATE KEY-----' 'MIIE' '-----END RSA PRIVATE KEY-----' 'plain' | bash "$HERE/mask.sh")"
if [[ "$masked" == *abc* || "$masked" == *'"p"'* || "$masked" == *pw@* || "$masked" == *ghp_* || "$masked" == *MIIE* ]] ||
  [[ "$masked" != *plain* ]]; then
  bad "mask.sh left a secret: $masked"
else
  ok "mask.sh masks keys, JSON, URLs, token shapes and PEM blocks"
fi

# snapshot.sh: the budget as hq.sh counts it, caps, use per container, switches only.
cat >"$T/snap-hq" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  --print-profile) echo full ;;
  "config --format json")
    if [[ "${HQ_ALL_PROFILES:-0}" == 1 ]]; then
      echo '{"services": {"api": {"restart": "unless-stopped", "deploy": {"resources": {"limits": {"memory": "536870912"}}}},
        "media-render": {"profiles": ["media"], "restart": "no", "deploy": {"resources": {"limits": {"memory": "1073741824"}}}},
        "ocr": {"profiles": ["ocr"], "restart": "unless-stopped", "deploy": {"resources": {"limits": {"memory": "268435456"}}}}}}'
    else
      echo '{"services": {"api": {"deploy": {"resources": {"limits": {"memory": "536870912"}}}},
        "ocr": {"profiles": ["ocr"], "deploy": {"resources": {"limits": {"memory": "268435456"}}}}}}'
    fi ;;
  "ps --all --format json")
    echo '{"Name": "coinepro-hq-api-1", "Service": "api", "State": "running", "Health": "healthy"}'
    echo '{"Name": "coinepro-hq-ocr-1", "Service": "ocr", "State": "running", "Health": ""}' ;;
esac
EOF
cat >"$T/snap-docker" <<'EOF'
#!/usr/bin/env bash
echo '{"Name": "coinepro-hq-api-1", "MemUsage": "301.5MiB / 512MiB", "CPUPerc": "1.25%"}'
echo '{"Name": "coinepro-hq-ocr-1", "MemUsage": "1.2GiB / 2GiB", "CPUPerc": "0.00%"}'
EOF
chmod +x "$T/snap-hq" "$T/snap-docker"
printf 'MemTotal:       15982592 kB\nMemAvailable:   10485760 kB\n' >"$T/meminfo"
printf 'HQ_OCR=on\nHQ_MEDIA=off\nPOSTGRES_PASSWORD=not-for-the-snapshot\n' >"$T/env"
snap="$(HQ_SH="$T/snap-hq" HQ_DOCKER="$T/snap-docker" HQ_MEMINFO="$T/meminfo" HQ_ENV_FILE="$T/env" \
  RUNTIME_DIRECTORY="$T/run" bash "$HERE/snapshot.sh")"
# full.env's HQ_BUDGET_PERCENT (86 by the owner's order, 2026-11-06), as hq.sh counts it
want='{"total_mb":15608,"budget_mb":13422,"caps_mb":768,"free_mb":12654,"available_mb":10240}'
if [[ "$(jq -c .memory <<<"$snap")" != "$want" ]]; then
  bad "snapshot memory: $(jq -c .memory <<<"$snap")"
elif [[ "$(jq -r '[.services[] | select(.service == "api") | .mem_used_mb, .cpu_percent, .state] | map(tostring) | join(" ")' <<<"$snap")" != "301.5 1.25 running" ]]; then
  bad "snapshot api use: $(jq -c '.services' <<<"$snap")"
elif [[ "$(jq -r '.services[] | select(.service == "ocr") | .mem_used_mb' <<<"$snap")" != 1228.8 ]]; then
  bad "snapshot GiB use: $(jq -c '.services' <<<"$snap")"
elif [[ "$(jq -r '.switches.ocr + " " + .switches.media' <<<"$snap")" != "on off" ]] || grep -q not-for-the-snapshot <<<"$snap"; then
  bad "snapshot switches: $(jq -c .switches <<<"$snap")"
elif [[ "$(jq -c '[.services[] | select(.service == "media-render") | .one_shot, .cap_mb, .state]' <<<"$snap")" != '[true,1024,"absent"]' ]]; then
  bad "snapshot media-render: $(jq -c .services <<<"$snap")"
else
  ok "snapshot: budget, caps, use per container, switches only"
fi

# A claim and a job's output never land in a json-file log (Alloy ships those to Loki).
if ! grep -q -- 'docker run --rm -i --init --log-driver none ' "$HERE/dispatch.sh"; then
  bad "the curl helper logs its answers (a claim, a job's output)"
else
  ok "no json-file log for the curl helper"
fi

if ((failed)); then exit 1; fi
echo "test-hubops: all ok"

# shellcheck shell=bash
# shellcheck disable=SC2154  # the values block of the rendered script sets them
# CoinePro HQ provisioning: run the plan's steps in order, then tell the hub
# once (the one-time callback token, valid 60 minutes, then shredded).
callback() {
  local token="$STATE/callback.token" header="$STATE/callback.header"
  if [[ ! -s "$token" ]]; then
    log "callback: already sent (or no token): the summary is in $STATE/results.jsonl"
    return 0
  fi
  python3 - "$STATE" "$RUN_ID" "$PLAN_REF" "${WORK_USER:-}" >"$STATE/callback.json" <<'PY'
import glob, json, os, sys
state, run, plan, user = sys.argv[1:5]
with open(os.path.join(state, "results.jsonl")) as f:
    results = [json.loads(line) for line in f if line.strip()]
deploy = None
pub = f"/home/{user}/.ssh/coinepro_deploy.pub"
if user and os.path.exists(pub):
    with open(pub) as f:
        deploy = f.read().strip()
hosts = []
for p in sorted(glob.glob("/etc/ssh/ssh_host_*_key.pub")):
    with open(p) as f:
        hosts.append(f.read().strip())
print(json.dumps({"run": run, "plan": plan, "failed": os.path.exists(os.path.join(state, "failed")),
                  "results": results, "deploy_key": deploy, "ssh_host_keys": hosts}))
PY
  # The token goes in a header read from a root-only file (-H @file), never
  # in curl's argv (another process could read it there) or in the URL.
  (
    umask 077
    printf 'Authorization: Bearer %s\n' "$(cat "$token")" >"$header"
  )
  if curl -fsS --max-time 30 --retry 10 --retry-delay 15 --retry-all-errors -o /dev/null \
    -H @"$header" -H 'Content-Type: application/json' \
    --data-binary @"$STATE/callback.json" "$CALLBACK_URL"; then
    log "callback: the hub has the results"
  else
    log "callback: the hub did not answer; the results stay in $STATE/results.jsonl"
  fi
  # One use only: the token, its header and cloud-init's copies of the user data go.
  shred -u "$token" "$header" 2>/dev/null || rm -f "$token" "$header"
  rm -f /var/lib/cloud/instance/user-data.txt* /var/lib/cloud/instance/scripts/part-* 2>/dev/null || true
}

main() {
  local key
  # A new try (after the reboot, or by hand) starts from the first step not done.
  rm -f "$STATE/failed"
  for key in $STEPS; do
    run_step "$key"
    [[ ! -e "$STATE/failed" ]] || break
  done
  callback
  systemctl disable coinepro-provision.service >/dev/null 2>&1 || true
  rm -f /etc/systemd/system/coinepro-provision.service
  if [[ -e "$STATE/failed" ]]; then
    log "finished with a failed step: see $LOG"
    exit 1
  fi
  log "finished: every step done"
}

main

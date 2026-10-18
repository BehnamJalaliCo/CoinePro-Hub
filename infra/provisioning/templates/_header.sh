# shellcheck shell=bash
# shellcheck disable=SC2154  # the values block above this header sets them
# CoinePro HQ provisioning: shared helpers (infra/provisioning/templates).
# Runs as root on the NEW server only, from cloud-init (and once more after
# the build's reboot). Every step is idempotent: a done step is skipped.
set -euo pipefail
umask 022
export DEBIAN_FRONTEND=noninteractive
STATE=/var/lib/coinepro-provision
LOG=/var/log/coinepro-provision.log
install -d -m 0700 "$STATE"
touch "$LOG" && chmod 0600 "$LOG"
exec > >(tee -a "$LOG") 2>&1

log() { printf '%s coinepro-provision: %s\n' "$(date -u +%FT%TZ)" "$*"; }

# result KEY OK(1|0) VERSION NOTE: one JSON line per step, for the hub's callback.
result() {
  python3 - "$@" >>"$STATE/results.jsonl" <<'PY'
import json, sys
key, ok, version, note = (sys.argv[1:] + ["", "", "", ""])[:4]
print(json.dumps({"key": key, "ok": ok == "1", "version": version[:120] or None,
                  "note": note[:300] or None}))
PY
}

apt_get() {
  apt-get -y -q -o DPkg::Lock::Timeout=600 -o Dpkg::Options::=--force-confdef \
    -o Dpkg::Options::=--force-confold "$@"
}

pkg_version() { dpkg-query -W -f='${Version}' "$1" 2>/dev/null || echo unknown; }

# The server's address on its Hetzner private network (metadata), or nothing.
private_ip() {
  curl -fsS --max-time 5 http://169.254.169.254/hetzner/v1/metadata/private-networks 2>/dev/null |
    sed -n 's/^-\{0,1\} *ip: *\([0-9.]*\).*/\1/p' | head -1
}

run_step() {
  local key="$1" fn="step_${1//-/_}"
  if [[ -e "$STATE/$key.done" ]]; then
    log "step $key: already done"
    return 0
  fi
  log "step $key: start"
  if "$fn"; then
    touch "$STATE/$key.done"
    log "step $key: done"
  else
    log "step $key: FAILED (the steps after it did not run)"
    result "$key" 0 "" "failed: see $LOG on the server"
    touch "$STATE/failed"
    return 1
  fi
}

# shellcheck shell=bash
# shellcheck disable=SC2154  # the values block above this header sets them
# CoinePro HQ provisioning: shared helpers (infra/provisioning/templates).
# Runs as root on the NEW server only, from cloud-init (and once more after
# the build's reboot). Every step is idempotent: a done step is skipped.
set -euo pipefail
shopt -s inherit_errexit
umask 022
export DEBIAN_FRONTEND=noninteractive
STATE=/var/lib/coinepro-provision
LOG=/var/log/coinepro-provision.log
# A step's exit code for "done, and this new server reboots now" (system-upgrade).
REBOOT_RC=100
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

# The server's address on its Hetzner private network (metadata), or nothing
# (never a failure: the steps that need it wait for it or say so).
private_ip() {
  local md
  md="$(curl -fsS --max-time 5 http://169.254.169.254/hetzner/v1/metadata/private-networks 2>/dev/null || true)"
  sed -n -e 's/^-\{0,1\} *ip: *\([0-9.]*\).*/\1/' -e T -e p -e q <<<"$md"
}

# run_step KEY: the step's function in a subshell with errexit ON, so ANY
# failing command fails the step (review 9.2 §1.1: bash turns errexit off
# inside a function that runs as an `if`, `||` or `&&` condition, and then
# only the step's last command counted). Never call run_step from such a
# condition either: main calls it as a plain command and reads $STATE/failed.
run_step() {
  local key="$1" fn="step_${1//-/_}" rc
  if [[ -e "$STATE/$key.done" ]]; then
    log "step $key: already done"
    return 0
  fi
  log "step $key: start"
  set +e
  (
    set -e
    "$fn"
  )
  rc=$?
  set -e
  if ((rc != 0 && rc != REBOOT_RC)); then
    log "step $key: FAILED (exit $rc; the steps after it did not run)"
    result "$key" 0 "" "failed (exit $rc): see $LOG on the server"
    touch "$STATE/failed"
    return 0
  fi
  touch "$STATE/$key.done"
  log "step $key: done"
  if ((rc == REBOOT_RC)); then
    # The step asked for the build's single reboot of THIS new server; the
    # remaining steps run after the boot (coinepro-provision.service).
    log "rebooting this new server once (its build only)"
    systemctl reboot
    exit 0
  fi
}

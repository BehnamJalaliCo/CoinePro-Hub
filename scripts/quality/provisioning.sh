#!/usr/bin/env bash
# The provisioning gate (prompt 09 §4): the cloud-init templates, rendered by
# the provisioner's own renderer, run in a throwaway Ubuntu 24.04 container as
# root, the way cloud-init runs them on a new Hetzner server:
#   complete  every software key's step ok; the work user with the owner's key,
#             locked password, valid sudoers; sshd -t accepts keys-only, no
#             root login; Docker's key fingerprint checked; the pinned Node
#             (sha256); the pinned Claude Code; a deploy key made there, its
#             public half reported; node-exporter on the private address;
#             ONE callback with the token in the header, then the token gone
#   again     run again: every step "already done", no second callback
#   reboot    an upgrade that needs a reboot reboots once and finishes after
#   failed    a wrong Docker key fingerprint stops the build there and says so
# Offline by default (--network none): apt, npm and the docker CLI are
# recording shims, the Docker key and the Node build come from the bench
# image (fetched and checked at its build), Hetzner's metadata from a fixture;
# everything else runs for real. HQ_PROVISION_ONLINE=1 runs "done" with the
# network and the real apt (full-upgrade), Docker's repository and npm; only
# systemctl (no systemd in a container) and the metadata stay shims.
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

BENCH="coinepro-hq/provision-bench:dev"
TEST_IMAGE="coinepro-hq/services-test:${HQ_TEST_IMAGE_TAG:-dev}"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
failed=0

docker build -q -t "$BENCH" "$REPO_DIR/infra/provisioning/test" >/dev/null
docker build -q -f "$REPO_DIR/services/Dockerfile.test" -t "$TEST_IMAGE" "$REPO_DIR/services" >/dev/null
docker run --rm --network none --user "$(id -u):$(id -g)" \
  -v "$REPO_DIR/services:/w:ro" -v "$REPO_DIR/infra/provisioning:/p:ro" -v "$T:/out" \
  "$TEST_IMAGE" python /p/test/render.py /out /p/templates
read -ra STEPS <"$T/steps" || true  # no trailing newline: read says EOF

bench() { # bench NAME NETWORK SCRIPT: one fresh container, SCRIPT as root inside
  local name="$1" net="$2" script="$3"
  if docker run --rm --network "$net" -v "$T:/ud:ro" -e PATH="/shims:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
    "$BENCH" bash -c "mkdir -p /bench/log /bench/installed /bench/out && chmod 1777 /bench/log &&
      ${ONLINE:+touch /bench/online &&} (python3 /bench/receiver.py &) && sleep 0.5 && $script" \
    >"$T/$name.log" 2>&1; then
    echo "provisioning: ok   $name"
  else
    echo "provisioning: FAIL $name" >&2
    tail -40 "$T/$name.log" >&2
    failed=1
  fi
}

ONLINE=""
if [[ "${HQ_PROVISION_ONLINE:-0}" == 1 ]]; then
  ONLINE=1
  bench online bridge "bash /ud/full.sh && python3 /bench/check.py done bx ${STEPS[*]}"
else
  bench complete none "bash /ud/full.sh && python3 /bench/check.py done bx ${STEPS[*]} &&
    /usr/local/sbin/coinepro-provision | grep -c 'already done' | grep -qx ${#STEPS[@]} &&
    python3 /bench/check.py done bx ${STEPS[*]}"
  bench reboot none "touch /var/run/reboot-required && bash /ud/full.sh && python3 /bench/check.py rebooted &&
    rm -f /var/run/reboot-required && /usr/local/sbin/coinepro-provision &&
    python3 /bench/check.py done bx ${STEPS[*]}"
  bench failed none "! bash /ud/bad-docker.sh && python3 /bench/check.py failed bx docker"
fi
grep -h '^ok\|^FAIL' "$T"/*.log | sort | uniq -c | sed 's/^ */provisioning:   /' | head -60
exit "$failed"

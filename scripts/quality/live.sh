#!/usr/bin/env bash
# Live checks against the running coinepro-hq stack (prompt 05 §1.6; the two
# live tests of 04.1 as automated ones). `make verify-live`, and a gate of
# `make check` that is skipped where no stack runs (CI: compose-rules covers
# the topology statically).
#   1.3   a throwaway container on hq-internal reaches neither OPA (8181),
#         Temporal (7233) nor the Tool Gateway (8080); the same probe on hq-core
#         does reach OPA (positive control: the probe can see a port).
#   1.12  a slow statement with a Persian parameter is logged (duration line)
#         without the parameter's value.
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

PROBE_IMAGE="busybox:1.38.0-musl"
PG="coinepro-hq-postgres-1"

if ! docker network inspect hq-internal >/dev/null 2>&1 ||
  [[ "$(docker inspect -f '{{.State.Running}}' coinepro-hq-opa-1 2>/dev/null)" != true ]]; then
  echo "live: skip (no running coinepro-hq stack here; compose-rules checks the topology)"
  exit 0
fi
failed=0
fail() { echo "live: FAIL $*" >&2; failed=1; }

probe() { # probe NETWORK HOST PORT -> 0 if a TCP connection opens
  docker run --rm --network "$1" "$PROBE_IMAGE" nc -z -w 3 "$2" "$3" >/dev/null 2>&1
}
ip_on() { # ip_on CONTAINER NETWORK
  docker inspect -f "{{(index .NetworkSettings.Networks \"$2\").IPAddress}}" "$1" 2>/dev/null || true
}

# ------------------------------------------------------------------ 1.3 ----
probe hq-core opa 8181 || fail "positive control: hq-core cannot reach opa:8181"
for target in opa:8181 temporal:7233 gateway:8080; do
  host="${target%:*}" port="${target#*:}"
  if probe hq-internal "$host" "$port"; then fail "hq-internal reaches $target"; fi
  ip="$(ip_on "coinepro-hq-$host-1" hq-core)"
  if [[ -n "$ip" ]] && probe hq-internal "$ip" "$port"; then fail "hq-internal reaches $host by IP ($ip)"; fi
done
echo "live: hq-internal reaches neither OPA, Temporal nor the gateway (hq-core reaches OPA)"

# ----------------------------------------------------------------- 1.12 ----
marker="آزمون-محرمانه-$(openssl rand -hex 6)"
since="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
docker exec -i "$PG" psql -U postgres -d postgres -v ON_ERROR_STOP=1 -qAt >/dev/null <<SQL
SELECT pg_sleep(1.2), \$1::text AS secret \bind '$marker' \g
SQL
sleep 1
logs="$(docker logs --since "$since" "$PG" 2>&1)"
grep -q 'duration:' <<<"$logs" || fail "positive control: the slow statement was not logged"
if grep -qF "$marker" <<<"$logs"; then fail "a statement parameter reached the log"; fi
echo "live: slow statement logged without its Persian parameter"

exit "$failed"

#!/usr/bin/env bash
# Live checks against the running coinepro-hq stack (prompt 05 §1.6; the two
# live tests of 04.1 as automated ones). `make verify-live`, and a gate of
# `make check` that is skipped where no stack runs (CI: compose-rules covers
# the topology statically).
#   1.3   a throwaway container on hq-internal reaches neither OPA (8181),
#         Temporal (7233) nor the Tool Gateway (8080), by name or by any of
#         their addresses; the same probe on hq-agent does reach OPA (positive
#         control: the probe can see a port).
#   1.12  a slow statement with a Persian parameter is logged (duration line)
#         without the parameter's value.
#   5.1 §2.9  from inside the web panel's own network namespace nothing but
#         Caddy answers (no data service, api, OpenBao, Prometheus, Loki, the
#         host's node-exporter, no internet); from inside the gateway's, the
#         api and OPA answer and neither Temporal, Postgres nor any other
#         data service does.
#   7.1 §2.19  egress and SearXNG probed by IP too (the neighbours, the
#         metadata address, the host's own addresses): a GAP line, not a
#         failure (closing it is the owner's DOCKER-USER rule).
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

PROBE_IMAGE="busybox:1.38.0-musl"
CURL_IMAGE="curlimages/curl:8.17.0"  # an HTTPS request through a proxy
PG="coinepro-hq-postgres-1"
WEB="coinepro-hq-web-1"
GATEWAY="coinepro-hq-gateway-1"

running() { [[ "$(docker inspect -f '{{.State.Running}}' "$1" 2>/dev/null)" == true ]]; }

if ! docker network inspect hq-internal >/dev/null 2>&1 || ! running coinepro-hq-opa-1; then
  echo "live: skip (no running coinepro-hq stack here; compose-rules checks the topology)"
  exit 0
fi
failures=0
fail() { echo "live: FAIL $*" >&2; failures=$((failures + 1)); }
ok() { # ok BEFORE MESSAGE: the message only when no check failed since BEFORE
  if ((failures == $1)); then echo "live: $2"; fi
}

probe() { # probe NETWORK HOST PORT -> 0 if a TCP connection opens
  docker run --rm --network "$1" "$PROBE_IMAGE" nc -z -w 3 "$2" "$3" >/dev/null 2>&1
}
probe_from() { # probe_from CONTAINER HOST PORT -> 0 if it opens from inside CONTAINER's netns
  docker run --rm --network "container:$1" "$PROBE_IMAGE" nc -z -w 3 "$2" "$3" >/dev/null 2>&1
}
ips_of() { # ips_of SERVICE -> every address of its container, on every network
  docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}' \
    "coinepro-hq-$1-1" 2>/dev/null || true
}
unreachable_from() { # unreachable_from CONTAINER LABEL SERVICE:PORT... (by name and by every IP)
  local from="$1" label="$2" target host port ip
  shift 2
  for target in "$@"; do
    host="${target%:*}" port="${target#*:}"
    if probe_from "$from" "$host" "$port"; then fail "$label reaches $target"; fi
    for ip in $(ips_of "$host"); do
      if probe_from "$from" "$ip" "$port"; then fail "$label reaches $host by IP ($ip:$port)"; fi
    done
  done
}

# ------------------------------------------------------------------ 1.3 ----
before=$failures
probe hq-agent opa 8181 || fail "positive control: hq-agent cannot reach opa:8181"
for target in opa:8181 temporal:7233 gateway:8080; do
  host="${target%:*}" port="${target#*:}"
  if probe hq-internal "$host" "$port"; then fail "hq-internal reaches $target"; fi
  for ip in $(ips_of "$host"); do
    if probe hq-internal "$ip" "$port"; then fail "hq-internal reaches $host by IP ($ip)"; fi
  done
done
ok "$before" "hq-internal reaches neither OPA, Temporal nor the gateway (hq-agent reaches OPA)"

# ------------------------------------------------------------ 5.1 §2.9 ----
DATA_SERVICES=(postgres:5432 valkey:6379 nats:4222 openbao:8200 llm-router:8000
  claude-runtime:8100 temporal:7233 temporal-ui:8080 prometheus:9090 loki:3100)
before=$failures
if running "$WEB"; then
  probe_from "$WEB" caddy 2020 || fail "positive control: the web cannot reach caddy:2020"
  unreachable_from "$WEB" web "${DATA_SERVICES[@]}" api:8000 opa:8181 gateway:8080 grafana:3000
  # The host's node-exporter listens on the hq-internal gateway address only.
  if probe_from "$WEB" 172.30.0.1 9100; then fail "web reaches node-exporter (172.30.0.1:9100)"; fi
  if probe_from "$WEB" 1.1.1.1 443; then fail "web reaches the internet (1.1.1.1:443)"; fi
  ok "$before" "the web reaches only Caddy (no data service, api, OpenBao, Prometheus, internet)"
else
  echo "live: web not running (HQ_WEB=off): web probe skipped"
fi
before=$failures
if running "$GATEWAY"; then
  probe_from "$GATEWAY" api 8000 || fail "positive control: the gateway cannot reach api:8000"
  probe_from "$GATEWAY" opa 8181 || fail "positive control: the gateway cannot reach opa:8181"
  unreachable_from "$GATEWAY" gateway "${DATA_SERVICES[@]}"
  if probe_from "$GATEWAY" 1.1.1.1 443; then fail "gateway reaches the internet (1.1.1.1:443)"; fi
  ok "$before" "the gateway reaches the api and OPA only (not Temporal, Postgres, any data service)"
else
  fail "the gateway is not running"
fi

# ------------------------------------------------------------- 07 §2 ----
# egress is the agents' only route out: it reaches the internet and SearXNG,
# and no data service, the api, OPA, OpenBao or Temporal; the browser reaches
# egress's proxy and nothing else (not even the internet); SearXNG reaches no
# service of the hub. (Private and metadata addresses on the internet side
# are refused by egress's guard: services/egress/tests.)
EGRESS="coinepro-hq-egress-1"
BROWSER="coinepro-hq-browser-1"
SEARXNG="coinepro-hq-searxng-1"
before=$failures
if running "$EGRESS"; then
  probe_from "$EGRESS" searxng 8080 || fail "positive control: egress cannot reach searxng:8080"
  probe_from "$EGRESS" 1.1.1.1 443 || fail "positive control: egress cannot reach the internet (1.1.1.1:443)"
  unreachable_from "$EGRESS" egress "${DATA_SERVICES[@]}" api:8000 opa:8181 grafana:3000 caddy:2020
  # The host's own addresses answer any container with a route out (no
  # iptables here: the owner's); node-exporter's metrics need its password.
  if docker run --rm --network "container:$EGRESS" "$PROBE_IMAGE" \
    wget -q -T 3 -O /dev/null http://172.30.0.1:9100/metrics >/dev/null 2>&1; then
    fail "egress reads node-exporter's metrics without the password (172.30.0.1:9100)"
  fi
  ok "$before" "egress reaches the internet and SearXNG only (no data service, api, OPA, OpenBao, Temporal)"
  before=$failures
  probe_from "$GATEWAY" egress 8090 || fail "positive control: the gateway cannot reach egress:8090"
  probe_from "$BROWSER" egress 3128 || fail "positive control: the browser cannot reach egress:3128"
  if probe_from "$BROWSER" 1.1.1.1 443; then fail "the browser reaches the internet directly (1.1.1.1:443)"; fi
  unreachable_from "$BROWSER" browser "${DATA_SERVICES[@]}" api:8000 opa:8181 gateway:8080 searxng:8080
  unreachable_from "$SEARXNG" searxng "${DATA_SERVICES[@]}" api:8000 opa:8181 gateway:8080
  ok "$before" "the browser reaches only egress's proxy; SearXNG reaches no service of the hub"
else
  fail "egress is not running"
fi

# ------------------------------------------------------------- 09 §4 ----
# The provisioner (opt-in profile "provisioning"): it reaches the api's
# internal endpoints, OpenBao (its AppRole) and egress's provisioner listener,
# which tunnels to api.hetzner.cloud:443 only; no data service, no internet of
# its own, nothing else through egress.
PROVISIONER="coinepro-hq-provisioner-1"
if running "$PROVISIONER"; then
  before=$failures
  probe_from "$PROVISIONER" api 8000 || fail "positive control: the provisioner cannot reach api:8000"
  probe_from "$PROVISIONER" egress 3130 || fail "positive control: the provisioner cannot reach egress:3130"
  if probe_from "$PROVISIONER" 1.1.1.1 443; then fail "the provisioner reaches the internet directly"; fi
  unreachable_from "$PROVISIONER" provisioner postgres:5432 valkey:6379 nats:4222 llm-router:8000 \
    gateway:8080 opa:8181 temporal:7233
  for port in 3128 3129 8090; do
    if probe_from "$PROVISIONER" egress "$port"; then fail "the provisioner reaches egress:$port"; fi
  done
  hz="$(docker run --rm --network "container:$PROVISIONER" "$CURL_IMAGE" -s -o /dev/null \
    -w '%{http_code}' -x http://egress:3130 https://api.hetzner.cloud/v1/locations || true)"
  [[ "$hz" == 401 ]] || fail "positive control: api.hetzner.cloud through egress answered $hz (want 401 without a token)"
  other="$(docker run --rm --network "container:$PROVISIONER" "$CURL_IMAGE" -s -o /dev/null \
    -w '%{http_code}' -x http://egress:3130 https://example.com/ || true)"
  [[ "$other" != 200 ]] || fail "the provisioner reaches another host through egress"
  ok "$before" "the provisioner reaches the api, OpenBao and api.hetzner.cloud (through egress) only"
fi

# ------------------------------------------------------- prompt 12 §4 ----
# The TTS one-shot's network (hq-tts, internal): the api and OpenBao only; no
# database, no other service of the hub, no internet, no neighbour. Probed on
# the network itself (the one-shot is not running between passes).
if docker network inspect hq-tts >/dev/null 2>&1; then
  before=$failures
  probe hq-tts api 8000 || fail "positive control: hq-tts cannot reach api:8000"
  probe hq-tts openbao 8200 || fail "positive control: hq-tts cannot reach openbao:8200"
  for target in postgres:5432 valkey:6379 nats:4222 llm-router:8000 gateway:8080 opa:8181 \
    temporal:7233 1.1.1.1:443 10.10.1.1:443; do
    if probe hq-tts "${target%%:*}" "${target##*:}"; then fail "hq-tts reaches $target"; fi
  done
  ok "$before" "hq-tts reaches the api and OpenBao only (no database, no internet)"
fi

# ------------------------------------------------------------ 7.1 §2.19 ----
# By address, beyond the hub's own services: the production neighbours
# (10.10.1.1-3), the cloud metadata address and the host's own addresses,
# from inside egress's and SearXNG's network namespaces (the two with a route
# out). Egress's guard refuses every one of them for an agent's request; the
# network itself does not, and closing that is the owner's DOCKER-USER rule
# (prompt 7.1 §0.4; nothing here touches iptables). So what answers is
# reported as a visible GAP line and does not fail the check.
GAP_PORTS="80 443"
gap_targets() {
  printf '%s\n' 10.10.1.1 10.10.1.2 10.10.1.3 169.254.169.254
  ip -o -4 addr show scope global 2>/dev/null | awk '{ split($4, a, "/"); print a[1] }'
}
open_by_ip() { # open_by_ip CONTAINER -> the "ip:port" of every target that opens, on one line
  local targets
  targets="$(gap_targets | sort -u | tr '\n' ' ')"
  # shellcheck disable=SC2016 # expanded by the probe's own shell
  docker run --rm --network "container:$1" -e TARGETS="$targets" -e PORTS="$GAP_PORTS" \
    "$PROBE_IMAGE" sh -c 'for ip in $TARGETS; do for port in $PORTS; do
      if nc -z -w 2 "$ip" "$port" >/dev/null 2>&1; then printf "%s:%s " "$ip" "$port"; fi
    done; done' 2>/dev/null || true
}
for c in "$EGRESS" "$SEARXNG"; do
  running "$c" || continue
  name="${c#coinepro-hq-}" name="${name%-1}"
  open="$(open_by_ip "$c")"
  if [[ -z "$open" ]]; then
    echo "live: $name reaches no neighbour (10.10.1.1-3), metadata or host address by IP"
    continue
  fi
  neighbours="" metadata="" host=0
  for hit in $open; do
    case "$hit" in
      10.10.1.[123]:*) neighbours+="$hit " ;;
      169.254.169.254:*) metadata+="$hit " ;;
      *) host=$((host + 1)) ;;
    esac
  done
  echo "live: GAP $name reaches by IP: neighbours [${neighbours% }], metadata [${metadata% }]," \
    "$host host address:port pairs of $(gap_targets | sort -u | wc -l | tr -d ' ') addresses x 80/443" \
    "(refused by egress's guard for agents; closing it at the network is the owner's DOCKER-USER rule)"
done

# ----------------------------------------------------------------- 1.12 ----
before=$failures
marker="آزمون-محرمانه-$(openssl rand -hex 6)"
since="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
docker exec -i "$PG" psql -U postgres -d postgres -v ON_ERROR_STOP=1 -qAt >/dev/null <<SQL
SELECT pg_sleep(1.2), \$1::text AS secret \bind '$marker' \g
SQL
sleep 1
logs="$(docker logs --since "$since" "$PG" 2>&1)"
grep -q 'duration:' <<<"$logs" || fail "positive control: the slow statement was not logged"
if grep -qF "$marker" <<<"$logs"; then fail "a statement parameter reached the log"; fi
ok "$before" "slow statement logged without its Persian parameter"

((failures == 0))

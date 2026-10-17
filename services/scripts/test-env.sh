#!/usr/bin/env bash
# Throwaway test dependencies for the Python code: Postgres (same image and
# init scripts as production) and NATS, on a private Docker network, plus the
# test image with the source mounted read-only.
#
# Usage: test-env.sh up            start deps (idempotent)
#        test-env.sh run <cmd...>  run a command in the test image (deps up)
#        test-env.sh down          remove the containers and network
#
# HQ_TEST_TARGET=api (apps/api) adds a Temporal dev server and OPA with the
# repo's policies, and runs apps/api's own test image with apps/api at /api.
# Nothing here touches the coinepro-hq stack or its volumes.
set -euo pipefail

SERVICES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_DIR="$(cd "$SERVICES_DIR/.." && pwd)"
API_DIR="$REPO_DIR/apps/api"
NAME="${HQ_TEST_NAME:-hq-test}"
TARGET="${HQ_TEST_TARGET:-services}"
NET="$NAME-net"
PG_IMAGE="pgvector/pgvector:0.8.7-pg17"
NATS_IMAGE="nats:2.15.1-alpine"
TEMPORAL_IMAGE="temporalio/admin-tools:1.32.1"
OPA_IMAGE="$(cat "$REPO_DIR/infra/opa/IMAGE" 2>/dev/null || true)"
STATE="${TMPDIR:-/tmp}/$NAME.env"

case "$TARGET" in
  services) TEST_IMAGE="coinepro-hq/services-test:dev" ;;
  api) TEST_IMAGE="coinepro-hq/api-test:dev" ;;
  *) echo "HQ_TEST_TARGET must be services or api" >&2; exit 2 ;;
esac

up() {
  if [[ "$TARGET" == api ]]; then
    docker build -q -f "$API_DIR/Dockerfile.test" -t "$TEST_IMAGE" "$API_DIR" >/dev/null
  else
    docker build -q -f "$SERVICES_DIR/Dockerfile.test" -t "$TEST_IMAGE" "$SERVICES_DIR" >/dev/null
  fi
  if ! docker inspect "$NAME-pg" >/dev/null 2>&1; then start; fi
  if [[ "$TARGET" == api ]] && ! docker inspect "$NAME-temporal" >/dev/null 2>&1; then start_api_deps; fi
  docker exec -i --env-file "$STATE" "$NAME-pg" bash -s <"$REPO_DIR/infra/postgres/provision.sh" >/dev/null
}

start() {
  umask 077
  {
    for v in POSTGRES_PASSWORD HQ_DB_PASSWORD TEMPORAL_DB_PASSWORD \
      TEMPORAL_VISIBILITY_DB_PASSWORD LLM_ROUTER_DB_PASSWORD HQ_API_DB_PASSWORD \
      HQ_WORKER_DB_PASSWORD NATS_PASSWORD; do
      printf '%s=%s\n' "$v" "$(openssl rand -hex 16)"
    done
  } >"$STATE"

  docker network create "$NET" >/dev/null
  docker run -d --name "$NAME-pg" --network "$NET" --network-alias postgres \
    --env-file "$STATE" -v "$REPO_DIR/infra/postgres/initdb:/docker-entrypoint-initdb.d:ro" \
    "$PG_IMAGE" -c shared_preload_libraries=pg_stat_statements \
    -c log_parameter_max_length=0 -c log_parameter_max_length_on_error=0 >/dev/null
  docker run -d --name "$NAME-nats" --network "$NET" --network-alias nats \
    --env-file "$STATE" -v "$REPO_DIR/infra/nats/nats-server.conf:/etc/nats/nats-server.conf:ro" \
    "$NATS_IMAGE" --config /etc/nats/nats-server.conf >/dev/null

  for _ in $(seq 1 60); do
    docker exec "$NAME-pg" psql -h 127.0.0.1 -U postgres -Atc 'SELECT 1' >/dev/null 2>&1 && break
    sleep 1
  done
}

start_api_deps() {
  [[ -n "$OPA_IMAGE" ]] || { echo "infra/opa/IMAGE is missing" >&2; exit 1; }
  docker run -d --name "$NAME-temporal" --network "$NET" --network-alias temporal \
    --entrypoint temporal "$TEMPORAL_IMAGE" server start-dev --ip 0.0.0.0 --headless \
    --log-level error --namespace default >/dev/null
  docker run -d --name "$NAME-opa" --network "$NET" --network-alias opa \
    -v "$REPO_DIR/infra/opa/policy:/policy:ro" "$OPA_IMAGE" \
    run --server --watch --authorization=basic --addr 0.0.0.0:8181 --log-level error /policy >/dev/null
}

run() {
  up
  # The role charters (agents/, read-only) are read by the api, worker and gateway.
  local mounts=(-v "$SERVICES_DIR:/w:ro" -v "$REPO_DIR/agents:/agents:ro")
  local extra=(-e HQ_AGENTS_DIR=/agents)
  if [[ "$TARGET" == api ]]; then
    mounts+=(-v "$API_DIR:/api:ro" -v "$REPO_DIR/infra/opa:/opa:ro")
    extra+=(-e TEST_TEMPORAL_ADDRESS=temporal:7233 -e TEST_OPA_URL=http://opa:8181)
  fi
  docker run --rm --network "$NET" --env-file "$STATE" \
    -e TEST_DB_HOST=postgres -e TEST_NATS_URL=nats://nats:4222 "${extra[@]}" \
    "${mounts[@]}" "$TEST_IMAGE" "$@"
}

down() {
  docker rm -f "$NAME-pg" "$NAME-nats" "$NAME-temporal" "$NAME-opa" >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
  rm -f "$STATE"
}

case "${1:-}" in
  up) up ;;
  run) shift; run "$@" ;;
  down) down ;;
  *) echo "usage: $0 up|run <cmd...>|down" >&2; exit 2 ;;
esac

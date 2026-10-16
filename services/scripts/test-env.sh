#!/usr/bin/env bash
# Throwaway test dependencies for the Python services: Postgres (same image and
# init scripts as production) and NATS, on a private Docker network, plus the
# test image with the source mounted read-only.
#
# Usage: test-env.sh up            start deps (idempotent)
#        test-env.sh run <cmd...>  run a command in the test image (deps up)
#        test-env.sh down          remove the containers and network
#
# Nothing here touches the coinepro-hq stack or its volumes.
set -euo pipefail

SERVICES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_DIR="$(cd "$SERVICES_DIR/.." && pwd)"
NAME="${HQ_TEST_NAME:-hq-test}"
NET="$NAME-net"
PG_IMAGE="pgvector/pgvector:0.8.7-pg17"
NATS_IMAGE="nats:2.15.1-alpine"
TEST_IMAGE="coinepro-hq/services-test:dev"
STATE="${TMPDIR:-/tmp}/$NAME.env"

up() {
  docker build -q -f "$SERVICES_DIR/Dockerfile.test" -t "$TEST_IMAGE" "$SERVICES_DIR" >/dev/null
  if ! docker inspect "$NAME-pg" >/dev/null 2>&1; then start; fi
  docker exec -i --env-file "$STATE" "$NAME-pg" bash -s <"$REPO_DIR/infra/postgres/provision.sh" >/dev/null
}

start() {
  umask 077
  {
    for v in POSTGRES_PASSWORD HQ_DB_PASSWORD TEMPORAL_DB_PASSWORD \
      TEMPORAL_VISIBILITY_DB_PASSWORD LLM_ROUTER_DB_PASSWORD NATS_PASSWORD; do
      printf '%s=%s\n' "$v" "$(openssl rand -hex 16)"
    done
  } >"$STATE"

  docker network create "$NET" >/dev/null
  docker run -d --name "$NAME-pg" --network "$NET" --network-alias postgres \
    --env-file "$STATE" -v "$REPO_DIR/infra/postgres/initdb:/docker-entrypoint-initdb.d:ro" \
    "$PG_IMAGE" -c shared_preload_libraries=pg_stat_statements >/dev/null
  docker run -d --name "$NAME-nats" --network "$NET" --network-alias nats \
    --env-file "$STATE" -v "$REPO_DIR/infra/nats/nats-server.conf:/etc/nats/nats-server.conf:ro" \
    "$NATS_IMAGE" --config /etc/nats/nats-server.conf >/dev/null

  for _ in $(seq 1 60); do
    docker exec "$NAME-pg" psql -h 127.0.0.1 -U postgres -Atc 'SELECT 1' >/dev/null 2>&1 && break
    sleep 1
  done
}

run() {
  up
  docker run --rm --network "$NET" --env-file "$STATE" \
    -e TEST_DB_HOST=postgres -e TEST_NATS_URL=nats://nats:4222 \
    -v "$SERVICES_DIR:/w:ro" "$TEST_IMAGE" "$@"
}

down() {
  docker rm -f "$NAME-pg" "$NAME-nats" >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
  rm -f "$STATE"
}

case "${1:-}" in
  up) up ;;
  run) shift; run "$@" ;;
  down) down ;;
  *) echo "usage: $0 up|run <cmd...>|down" >&2; exit 2 ;;
esac

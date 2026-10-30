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

# HQ_TEST_IMAGE_TAG: a tag of its own for each checkout that tests at the same
# time (parallel worktrees), so one never runs the other's freshly built image.
TAG="${HQ_TEST_IMAGE_TAG:-dev}"
case "$TARGET" in
  services) TEST_IMAGE="coinepro-hq/services-test:$TAG" ;;
  api) TEST_IMAGE="coinepro-hq/api-test:$TAG" ;;
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
  # The provisioner's reviewed cloud-init templates (prompt 09 §4), read-only.
  mounts+=(-v "$REPO_DIR/infra/provisioning/templates:/templates:ro")
  extra+=(-e HQ_PROVISION_TEMPLATES=/templates)
  # The companies' flat marks and the design tokens (prompt 9.1: the brand seed), read-only.
  mounts+=(-v "$REPO_DIR/design/brand/companies:/brands:ro" -v "$REPO_DIR/design/tokens:/design-tokens:ro")
  extra+=(-e HQ_BRANDS_DIR=/brands -e HQ_DESIGN_TOKENS=/design-tokens/divan.tokens.json)
  # IRANYekanX for a creative's Persian overlay (prompt 12 §9.1), read-only.
  mounts+=(-v "$REPO_DIR/design/fonts/static:/fonts:ro")
  extra+=(-e HQ_FONTS_DIR=/fonts)
  # The substitute players' reviewed web recipes (prompt 12 §9.1), read-only.
  mounts+=(-v "$REPO_DIR/infra/egress/recipes:/recipes:ro")
  extra+=(-e HQ_EGRESS_RECIPES=/recipes)
  # The archive's open layer seeds (prompt 14 §2: classes, levels, rules...), read-only.
  mounts+=(-v "$REPO_DIR/infra/seed/archive:/archive-seed:ro")
  extra+=(-e HQ_ARCHIVE_SEED=/archive-seed)
  if [[ "$TARGET" == api ]]; then
    mounts+=(-v "$API_DIR:/api:ro" -v "$REPO_DIR/infra/opa:/opa:ro")
    extra+=(-e TEST_TEMPORAL_ADDRESS=temporal:7233 -e TEST_OPA_URL=http://opa:8181)
    # Prompt 12 §14: the reviewed allow-list of MCP container servers and their
    # compose services (the tests compare the two), read-only.
    mounts+=(-v "$REPO_DIR/infra/mcp:/mcp:ro" -v "$REPO_DIR/infra/compose/mcp.yaml:/mcp-compose/mcp.yaml:ro")
    extra+=(-e HQ_MCP_ALLOWLIST=/mcp/servers.yaml)
  fi
  docker run --rm --network "$NET" --env-file "$STATE" \
    -e TEST_DB_HOST=postgres -e TEST_NATS_URL=nats://nats:4222 "${extra[@]}" \
    "${mounts[@]}" "$TEST_IMAGE" "$@"
}

down() {
  # -v: their anonymous volumes (a Postgres data dir each) go with them
  docker rm -fv "$NAME-pg" "$NAME-nats" "$NAME-temporal" "$NAME-opa" >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
  rm -f "$STATE"
}

case "${1:-}" in
  up) up ;;
  run) shift; run "$@" ;;
  down) down ;;
  *) echo "usage: $0 up|run <cmd...>|down" >&2; exit 2 ;;
esac

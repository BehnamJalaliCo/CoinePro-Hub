#!/usr/bin/env bash
# Python gates for services/ and apps/api, each in its hash-pinned test image:
#   python.sh lint     ruff (lint + format) and mypy --strict
#   python.sh test     pytest on real Postgres + NATS (+ Temporal + OPA for
#                      apps/api), all throwaway, with coverage:
#                        services: >= 85% router logic, >= 80% overall
#                        apps/api: >= 85% domain logic, >= 80% overall
#                      (apps/api's tests also check the committed OpenAPI
#                      document and fuzz every operation with Schemathesis)
#   python.sh audit    pip-audit of every lock file (known CVEs)
#   python.sh openapi  rewrite apps/api/openapi/hq-api.v1.json from the code
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

TE="$REPO_DIR/services/scripts/test-env.sh"
API_DIR="$REPO_DIR/apps/api"
API_IMAGE="coinepro-hq/api-test:dev"
export HQ_TEST_NAME="hq-check-$$"
trap '"$TE" down' EXIT

# Domain logic of apps/api held to 85% (prompt 04 §10): delegation, budgets,
# decisions, notifications and Khalvat, codes and templates, identity.
API_DOMAIN="*/hq_api/domain/work.py,*/hq_api/domain/decisions.py,*/hq_api/domain/notify.py,\
*/hq_api/domain/org.py,*/hq_api/domain/templates.py,*/hq_api/domain/recurrence.py,\
*/hq_api/domain/recurring.py,*/hq_api/domain/control.py,*/hq_api/security/*,*/hq_api/routes/auth.py"

api_image() { # api_image <cmd...>: apps/api's test image without the test dependencies
  docker build -q -f "$API_DIR/Dockerfile.test" -t "$API_IMAGE" "$API_DIR" >/dev/null
  docker run --rm --user "$(id -u):$(id -g)" -v "$REPO_DIR/services:/w:ro" "$@"
}

case "${1:-}" in
  lint)
    "$TE" run sh -c 'ruff check --no-cache . && ruff format --no-cache --check . &&
      mypy hq-common/src llm-router/src claude-runtime/src claude-runtime/testing'
    api_image -v "$API_DIR:/api:ro" -w /api "$API_IMAGE" sh -c \
      'ruff check --no-cache . && ruff format --no-cache --check . && mypy src'
    ;;
  test)
    "$TE" run sh -c 'pytest hq-common/tests llm-router/tests claude-runtime/tests \
      --cov=hq_common --cov=llm_router --cov=claude_runtime --cov-report=term --cov-fail-under=80 &&
      coverage report --fail-under=85 \
        --include="*/llm_router/assignment.py,*/llm_router/budget.py,*/llm_router/scheduler.py,*/llm_router/breaker.py"'
    HQ_TEST_TARGET=api "$TE" run sh -c "cd /api && pytest tests --cov=hq_api --cov-report=term \
      --cov-fail-under=80 && coverage report --fail-under=85 --include='$API_DOMAIN'"
    ;;
  audit)
    "$TE" run pip-audit --progress-spinner off --require-hashes --disable-pip \
      -r llm-router/requirements.lock -r claude-runtime/requirements.lock
    api_image -v "$API_DIR:/api:ro" -w /api "$API_IMAGE" pip-audit --progress-spinner off \
      --require-hashes --disable-pip -r requirements.lock
    ;;
  openapi)
    api_image -v "$API_DIR:/api" -w /api "$API_IMAGE" python -m hq_api.openapi_export
    ;;
  *) echo "usage: $0 lint|test|audit|openapi" >&2; exit 2 ;;
esac

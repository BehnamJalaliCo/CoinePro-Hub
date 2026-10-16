#!/usr/bin/env bash
# Python services gates, in the hash-pinned test image:
#   python.sh lint   ruff (lint + format) and mypy --strict
#   python.sh test   pytest on real Postgres + NATS (throwaway) with coverage:
#                    >= 85% for the router logic (assignment, budget, queue,
#                    breaker) and >= 80% overall
#   python.sh audit  pip-audit of both service lock files (known CVEs)
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

TE="$REPO_DIR/services/scripts/test-env.sh"
export HQ_TEST_NAME="hq-check-$$"
trap '"$TE" down' EXIT

case "${1:-}" in
  lint)
    "$TE" run sh -c 'ruff check --no-cache . && ruff format --no-cache --check . &&
      mypy hq-common/src llm-router/src claude-runtime/src claude-runtime/testing'
    ;;
  test)
    "$TE" run sh -c 'pytest hq-common/tests llm-router/tests claude-runtime/tests \
      --cov=hq_common --cov=llm_router --cov=claude_runtime --cov-report=term --cov-fail-under=80 &&
      coverage report --fail-under=85 \
        --include="*/llm_router/assignment.py,*/llm_router/budget.py,*/llm_router/scheduler.py,*/llm_router/breaker.py"'
    ;;
  audit)
    "$TE" run pip-audit --progress-spinner off --require-hashes --disable-pip \
      -r llm-router/requirements.lock -r claude-runtime/requirements.lock
    ;;
  *) echo "usage: $0 lint|test|audit" >&2; exit 2 ;;
esac

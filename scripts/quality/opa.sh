#!/usr/bin/env bash
# OPA policies (infra/opa/policy): strict compile, formatting, the unit tests,
# and 100% test coverage of every rule, in the pinned OPA image.
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

OPA_IMAGE="$(cat "$REPO_DIR/infra/opa/IMAGE")"  # single source: compose, test-env and this gate
POLICY_DIR="$REPO_DIR/infra/opa/policy"

opa() {
  docker run --rm --user "$(id -u):$(id -g)" -v "$POLICY_DIR:/policy:ro" -w /policy "$OPA_IMAGE" "$@"
}

opa check --strict /policy
opa fmt --diff --fail /policy
opa test /policy

if ! opa test --coverage --threshold 100 /policy >/dev/null; then
  # Show what is not covered (the threshold run prints no report).
  opa test --coverage /policy | jq -r '"coverage: \(.coverage)%",
    (.files | to_entries[] | select(.value.not_covered != null)
      | "  \(.key): lines \(.value.not_covered | map("\(.start.row)-\(.end.row)") | join(", "))")' >&2
  echo "opa: coverage below 100%" >&2
  exit 1
fi
echo "opa: policies ok (100% coverage)"

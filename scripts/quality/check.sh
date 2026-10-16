#!/usr/bin/env bash
# Runs every quality gate (make check, and CI on each push).
# Prints PASS/FAIL per gate and exits non-zero if any failed.
set -uo pipefail
QUALITY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

GATES=(gitleaks compose-config ports compose-rules memory-budget shellcheck yamllint)
failed=()
for gate in "${GATES[@]}"; do
  echo "--- $gate"
  if "$QUALITY_DIR/$gate.sh"; then
    echo "PASS $gate"
  else
    echo "FAIL $gate"
    failed+=("$gate")
  fi
done

echo "---"
if ((${#failed[@]})); then
  echo "check: FAILED (${failed[*]})"
  exit 1
fi
echo "check: all ${#GATES[@]} gates passed"

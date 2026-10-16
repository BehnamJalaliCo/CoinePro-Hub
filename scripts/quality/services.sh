#!/usr/bin/env bash
# All Python service gates at once (make test-services).
set -euo pipefail
QUALITY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$QUALITY_DIR/hadolint.sh"
for step in lint test audit; do
  "$QUALITY_DIR/python.sh" "$step"
done

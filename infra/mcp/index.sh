#!/usr/bin/env bash
# The CodeCortex index job's host side (prompt 12 §14.6; `make mcp-index`,
# systemd coinepro-hq-mcp-index.timer nightly at 03:30 Tehran and
# coinepro-hq-mcp-index.path when the hub repository's HEAD moves): runs the
# one-shot service mcp-codecortex-index (network none; the repository
# read-only; it writes only its own volumes), which skips a copy already
# indexed at HEAD unless --full. Rule-only (no model, no outside call), so it
# also runs while the holding's kill switch is engaged. Nothing while the
# mcp profile is off (HQ_MCP); hq.sh refuses it while it does not fit.
set -euo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${HQ_ENV_FILE:-$REPO_DIR/infra/compose/.env}"
mcp="${HQ_MCP:-$(sed -n 's/^HQ_MCP=//p' "$ENV_FILE" 2>/dev/null | tail -n1)}"
if [[ "$mcp" != on ]]; then
  echo "mcp-index: the mcp profile is off (HQ_MCP); nothing to index"
  exit 0
fi
exec "$REPO_DIR/infra/compose/hq.sh" run --rm --no-deps mcp-codecortex-index "$@"

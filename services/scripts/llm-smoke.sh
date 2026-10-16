#!/usr/bin/env bash
# One tiny REAL call through the whole path (prompt 03 §8): Haiku, effort low,
# "Just write OK". Prints the response, the ledger row and the NATS event.
# The caller token goes in on stdin.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TOKEN_FILE="${HQ_SECRETS_DIR:-/home/Hub/.secrets}/llm-router-caller-hq-ops.token"
[[ -r "$TOKEN_FILE" ]] || { echo "llm-smoke: $TOKEN_FILE missing (run make up)" >&2; exit 1; }
"$REPO_DIR/infra/compose/hq.sh" exec -T llm-router python -m llm_router.smoke <"$TOKEN_FILE"

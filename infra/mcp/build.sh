#!/usr/bin/env bash
# Builds every MCP container server of the reviewed allow-list
# (infra/mcp/servers.yaml; prompt 12 §14; `make mcp-build`) reproducibly:
# SOURCE_DATE_EPOCH=0, rewritten timestamps, no provenance or SBOM
# attestations, so the same Dockerfile and hash-pinned locks always give the
# same image digest. Each build must give exactly the digest the allow-list
# (and infra/compose/mcp.yaml) names; otherwise it fails and prints both: a
# new digest goes in only as a reviewed change to those files.
# Env: MCP_BUILD_TAG (default 0.1.0; another tag for a test build).
# --if-on: only while the mcp profile is switched on (HQ_MCP=on; make up).
set -euo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LIST="$REPO_DIR/infra/mcp/servers.yaml"
if [[ "${1:-}" == --if-on ]]; then
  env_file="${HQ_ENV_FILE:-$REPO_DIR/infra/compose/.env}"
  mcp="${HQ_MCP:-$(sed -n 's/^HQ_MCP=//p' "$env_file" 2>/dev/null | tail -n1)}"
  [[ "$mcp" == on ]] || exit 0
fi
TAG="${MCP_BUILD_TAG:-0.1.0}"
failed=0
keys="$(sed -n 's/^  - key: \([a-z0-9-]*\)$/\1/p' "$LIST")"
for key in $keys; do
  entry="$(sed -n "/^  - key: $key\$/,/^  - key:/p" "$LIST")"
  image="$(sed -n 's/^    image: //p' <<<"$entry")"
  file="$(sed -n 's/^    build: //p' <<<"$entry")"
  name="${image%%:*}"
  want="${image##*@}"
  [[ -n "$file" && -f "$REPO_DIR/$file" ]] || { echo "mcp-build: $key: no Dockerfile ($file)" >&2; failed=1; continue; }
  have="$(SOURCE_DATE_EPOCH=0 docker buildx build --quiet --provenance=false --sbom=false \
    --build-arg SOURCE_DATE_EPOCH=0 \
    --output "type=image,name=$name:$TAG,rewrite-timestamp=true" \
    -f "$REPO_DIR/$file" "$REPO_DIR/infra/mcp")"
  if [[ "$have" == "$want" ]]; then
    echo "mcp-build: $key ok ($name:$TAG@$have)"
  else
    echo "mcp-build: $key built $have, but the allow-list names $want" >&2
    echo "           (a different digest is a reviewed change to infra/mcp/servers.yaml and infra/compose/mcp.yaml)" >&2
    failed=1
  fi
done
exit "$failed"

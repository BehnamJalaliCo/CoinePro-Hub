#!/usr/bin/env bash
# Imports automations/n8n/*.json into the running n8n (prompt 22, contract §30.4) and
# activates them. The workflow files are the reviewed source; importing again replaces a
# workflow with the same id. Run after `make n8n-on`.
#   make n8n-import
set -euo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HQ="$REPO_DIR/infra/compose/hq.sh"
DIR="$REPO_DIR/automations/n8n"

shopt -s nullglob
files=("$DIR"/*.json)
((${#files[@]})) || { echo "n8n-import: no workflow files in automations/n8n" >&2; exit 1; }
for f in "${files[@]}"; do
  jq -e 'type == "object" and (.nodes | type == "array") and (.id | type == "string")' "$f" >/dev/null ||
    { echo "n8n-import: $(basename "$f") is not a workflow with an id" >&2; exit 1; }
done

# The compose service mounts automations/n8n read-only at /workflows.
"$HQ" --profile automations exec -T n8n n8n import:workflow --separate --input=/workflows
# Activation: the command's name changed between n8n versions; the first that works counts.
if "$HQ" --profile automations exec -T n8n n8n publish:workflow --all >/dev/null 2>&1; then
  echo "n8n-import: workflows published"
elif "$HQ" --profile automations exec -T n8n n8n update:workflow --all --active=true >/dev/null 2>&1; then
  echo "n8n-import: workflows activated"
else
  echo "n8n-import: imported; activate them once in the editor (127.0.0.1:5678)" >&2
fi
# Webhooks register when n8n starts: restart it so the activated workflows listen.
"$HQ" --profile automations restart n8n >/dev/null
echo "n8n-import: ${#files[@]} workflow file(s) imported"

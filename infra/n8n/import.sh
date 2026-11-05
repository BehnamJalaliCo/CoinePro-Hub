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
# Activation, one workflow at a time by its id (23.1: in n8n 2.x `publish:workflow --all` is refused
# and `update:workflow --all --active=true` exits 0 without activating anything, so the webhooks
# stayed unregistered). n8n 2.x publishes with `publish:workflow --id`; 1.x activates with
# `update:workflow --id --active=true`.
not_active=()
for f in "${files[@]}"; do
  id="$(jq -r .id "$f")"
  if "$HQ" --profile automations exec -T n8n n8n publish:workflow --id="$id" >/dev/null 2>&1 ||
    "$HQ" --profile automations exec -T n8n n8n update:workflow --id="$id" --active=true >/dev/null 2>&1; then
    echo "n8n-import: $id published"
  else
    not_active+=("$id")
  fi
done
if ((${#not_active[@]})); then
  echo "n8n-import: not activated: ${not_active[*]}; activate them once in the editor (127.0.0.1:5678)" >&2
fi
# Webhooks register when n8n starts: restart it so the activated workflows listen.
"$HQ" --profile automations restart n8n >/dev/null
echo "n8n-import: ${#files[@]} workflow file(s) imported"

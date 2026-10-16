#!/usr/bin/env bash
# hadolint for every Dockerfile in the repo.
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

mapfile -t files < <(repo_files '*Dockerfile*' | grep -v '\.dockerignore$')
for f in "${files[@]}"; do
  docker run --rm -i "$HADOLINT_IMAGE" hadolint --failure-threshold warning - <"$REPO_DIR/$f"
done
echo "hadolint: ${#files[@]} Dockerfiles ok"

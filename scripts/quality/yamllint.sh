#!/usr/bin/env bash
# yamllint (pinned version, run in a throwaway Python container).
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

mapfile -t files < <(repo_files '*.yml' '*.yaml')
docker run --rm -v "$REPO_DIR:/repo:ro" -w /repo "$PYTHON_IMAGE" sh -c \
  'pip install --quiet --disable-pip-version-check --root-user-action=ignore "yamllint==$0" && yamllint --strict -c .yamllint.yaml "$@"' \
  "$YAMLLINT_VERSION" "${files[@]}"
echo "yamllint: ${#files[@]} files ok"

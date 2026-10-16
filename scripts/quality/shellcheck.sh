#!/usr/bin/env bash
# Lints every shell script in the repo with ShellCheck.
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

mapfile -t scripts < <(repo_files '*.sh')
docker run --rm -v "$REPO_DIR:/mnt:ro" -w /mnt "$SHELLCHECK_IMAGE" --external-sources --source-path=SCRIPTDIR "${scripts[@]}"
echo "shellcheck: ${#scripts[@]} scripts ok"

#!/usr/bin/env bash
# Secret scan with gitleaks: the full git history, then the working tree
# (tracked files plus new files that are not ignored, so .env stays out).
# --redact keeps any finding's value out of the output.
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

gitleaks() {
  docker run --rm --user "$(id -u):$(id -g)" "$@"
}

# In a git worktree .git is a file naming the main repository's git dir by its
# absolute path: mount that dir at the same path, or there is no history to scan.
common="$(cd "$REPO_DIR" && cd "$(git rev-parse --git-common-dir)" && pwd)"
mounts=(-v "$REPO_DIR:/repo:ro")
[[ "$common" == "$REPO_DIR/.git" ]] || mounts+=(-v "$common:$common:ro")
gitleaks "${mounts[@]}" \
  -e GIT_CONFIG_COUNT=1 -e GIT_CONFIG_KEY_0=safe.directory -e GIT_CONFIG_VALUE_0=/repo \
  "$GITLEAKS_IMAGE" git --no-banner --redact --verbose --exit-code 1 --log-level warn /repo
echo "gitleaks: git history clean"

tree="$(mktemp -d)"
trap 'rm -rf "$tree"' EXIT
git -C "$REPO_DIR" ls-files -z --cached --others --exclude-standard |
  (cd "$REPO_DIR" && xargs -0 cp --parents -t "$tree")
gitleaks -v "$tree:/scan:ro" \
  "$GITLEAKS_IMAGE" dir --no-banner --redact --verbose --exit-code 1 --log-level warn /scan
echo "gitleaks: working tree clean"

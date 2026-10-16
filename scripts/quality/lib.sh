# shellcheck shell=bash
# shellcheck disable=SC2034 # the variables are used by the scripts that source this file
# Shared helpers for the quality gates. Sourced, not executed.
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HQ="$REPO_DIR/infra/compose/hq.sh"
PROFILES=(lean full)

GITLEAKS_IMAGE="zricethezav/gitleaks:v8.30.1"
SHELLCHECK_IMAGE="koalaman/shellcheck:v0.11.0"
PYTHON_IMAGE="python:3.13.16-alpine"
YAMLLINT_VERSION="1.38.0"

# Compose needs a secrets file to render. Outside the server (CI, a laptop)
# use a throwaway one with random values.
ensure_env() {
  if [[ -z "${HQ_ENV_FILE:-}" && ! -r "$REPO_DIR/infra/compose/.env" ]]; then
    QUALITY_TMP="$(mktemp -d)"
    trap 'rm -rf "$QUALITY_TMP"' EXIT
    "$REPO_DIR/infra/compose/gen-env.sh" --output "$QUALITY_TMP/.env" >/dev/null
    export HQ_ENV_FILE="$QUALITY_TMP/.env"
  fi
}

# Rendered compose model (JSON) for one profile.
compose_json() {
  HQ_PROFILE="$1" "$HQ" config --format json
}

# Tracked files plus new files that are not ignored.
repo_files() {
  git -C "$REPO_DIR" ls-files --cached --others --exclude-standard -- "$@"
}

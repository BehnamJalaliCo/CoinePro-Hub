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
HADOLINT_IMAGE="hadolint/hadolint:v2.15.1"

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

# Rendered compose model (JSON) for one profile, plus any opt-in profiles:
# compose_json PROFILE [OPT_IN_PROFILE...]
compose_json() {
  local profile="$1" extra=() p
  shift
  for p in "$@"; do extra+=(--profile "$p"); done
  HQ_PROFILE="$profile" "$HQ" "${extra[@]}" config --format json
}

# Compose profiles an operator may add by hand (e.g. cadvisor): every profile
# of compose.yaml but the memory profiles and "web" (hq.sh switches it on).
opt_in_profiles() {
  HQ_PROFILE=lean "$HQ" config --profiles | grep -vxE "$(IFS='|'; echo "${PROFILES[*]}")|web" || true
}

# Tracked files plus new files that are not ignored.
repo_files() {
  git -C "$REPO_DIR" ls-files --cached --others --exclude-standard -- "$@"
}

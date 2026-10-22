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
  for p in "${ALWAYS_COUNTED[@]}" "$@"; do extra+=(--profile "$p"); done
  # Opt-in profiles come from the arguments only (never from .env's HQ_STT).
  HQ_PROFILE="$profile" HQ_STT=off HQ_PROVISIONING=off HQ_SUBSTITUTES=off HQ_SUBSTITUTES_WEB=off \
    "$HQ" "${extra[@]}" config --format json
}

# Profiles of jobs that run outside `compose up` (backup-tools: the hourly
# backup's `docker run`, 7.1 §3): in every model the gates check, so they are
# always counted in the memory budget and follow the house rules.
ALWAYS_COUNTED=(backup-tools)

# Whether an opt-in profile is switched on on this server: HQ_<NAME>=on in the
# environment or in .env (e.g. HQ_STT=on for "stt"). CI has none on.
opt_in_enabled() { # opt_in_enabled NAME
  local var value env_file="${HQ_ENV_FILE:-$REPO_DIR/infra/compose/.env}"
  var="HQ_$(tr '[:lower:]-' '[:upper:]_' <<<"$1")"
  value="${!var:-}"
  if [[ -z "$value" && -r "$env_file" ]]; then value="$(sed -n "s/^$var=//p" "$env_file" | tail -n1)"; fi
  [[ "$value" == on ]]
}

# Compose profiles an operator may add by hand (e.g. cadvisor): every profile
# of compose.yaml but the memory profiles, "web" (hq.sh switches it on) and
# the always-counted ones.
opt_in_profiles() {
  HQ_PROFILE=lean HQ_STT=off HQ_PROVISIONING=off HQ_SUBSTITUTES=off HQ_SUBSTITUTES_WEB=off \
    "$HQ" config --profiles |
    grep -vxE "$(IFS='|'; echo "${PROFILES[*]}")|web|$(IFS='|'; echo "${ALWAYS_COUNTED[*]}")" || true
}

# Tracked files plus new files that are not ignored.
repo_files() {
  git -C "$REPO_DIR" ls-files --cached --others --exclude-standard -- "$@"
}

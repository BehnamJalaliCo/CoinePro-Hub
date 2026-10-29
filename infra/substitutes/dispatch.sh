#!/usr/bin/env bash
# The substitute players' host dispatcher (prompt 12 §9.1, contract §21.13),
# run every 20 s by coinepro-hq-substitutes.timer as user Hub. One job at a
# time for both players (flock): claim it from the api, run it in one
# one-shot substitute-runner container (the Job JSON on its stdin, its JSON
# lines back), relay a sign-in's events and the owner's code, post `done`.
#
# - Off unless HQ_SUBSTITUTES=on (and the profile fits: hq.sh refuses it
#   otherwise) and the dispatcher's api token exists: it exits at once.
# - The api answers no job while the holding's kill switch is engaged
#   (prompt 12 §0, the launch gate): nothing reaches a CLI, nothing leaves.
# - The api has no published port: every call goes through a short-lived
#   curl container on hq-internal, its token in a header file (600) mounted
#   read-only, never on a command line.
# - A code review (seat code_review) gets a read-only checkout of the
#   repository at head_sha: `git archive` from the hub's own clone (the
#   mapping HQ_SUBSTITUTE_REPOS, default coinepro-hub=/home/Hub/CoinePro-Hub),
#   every file the secret scan flags removed (hq_common.secret_files) before
#   the CLI ever sees it. An unknown repository or commit: `no_access`.
# - Nothing a job carries (the question, a code) is ever printed or logged.
#
# Usage: dispatch.sh   (the timer runs it; tests set HQ_SH, HQ_SUBSTITUTE_CURL)
set -euo pipefail
umask 077

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HQ="${HQ_SH:-$REPO_DIR/infra/compose/hq.sh}"
ENV_FILE="${HQ_ENV_FILE:-$REPO_DIR/infra/compose/.env}"
SECRETS_DIR="${HQ_SECRETS_DIR:-/home/Hub/.secrets}"
AUTH_FILE="$SECRETS_DIR/substitutes/api-auth" # "Authorization: Bearer ..." (600)
CURL_IMAGE="curlimages/curl:8.17.0"
API_NET="${HQ_SUBSTITUTE_API_NET:-hq-internal}"
API_URL="${HQ_SUBSTITUTE_API_URL:-http://api:8000}"
WORK_ROOT="${RUNTIME_DIRECTORY:-${XDG_RUNTIME_DIR:-/tmp}}"
CODE_POLL_S="${HQ_SUBSTITUTE_CODE_POLL_S:-3}"

env_value() { # env_value NAME: the environment's value, else .env's
  local v="${!1:-}"
  if [[ -z "$v" && -r "$ENV_FILE" ]]; then v="$(sed -n "s/^$1=//p" "$ENV_FILE" | tail -n1)"; fi
  printf '%s' "$v"
}

[[ "$(env_value HQ_SUBSTITUTES)" == on ]] || exit 0
if [[ ! -r "$AUTH_FILE" ]]; then
  echo "substitutes: no dispatcher token yet ($AUTH_FILE; make up makes it)" >&2
  exit 0
fi
exec 9>"$WORK_ROOT/substitutes.lock"
flock -n 9 || exit 0 # one job at a time, for both players together

work="$(mktemp -d "$WORK_ROOT/job.XXXXXX")"
trap 'chmod -R u+w "$work" 2>/dev/null; rm -rf "$work"' EXIT

api() { # api PATH [JSON_BODY_ON_STDIN]: POST to the api's internal route, the answer on stdout
  if [[ -n "${HQ_SUBSTITUTE_CURL:-}" ]]; then # tests: a fake api
    "$HQ_SUBSTITUTE_CURL" "$1"
    return
  fi
  # curl reads its body before its own -m clock starts: if the docker client
  # goes away before stdin closes, only the in-container timeout ends it
  # (under --init: curl as PID 1 would ignore its SIGTERM).
  docker run --rm -i --init --network "$API_NET" --read-only --cap-drop ALL \
    --security-opt no-new-privileges:true --user "$(id -u):$(id -g)" --memory 32m \
    -v "$AUTH_FILE:/run/auth:ro" --entrypoint timeout "$CURL_IMAGE" \
    45 curl -sS -m 30 -X POST -H @/run/auth -H 'Content-Type: application/json' \
    --data-binary @- "$API_URL$1"
}

repo_path() { # repo_path NAME: the hub's own clone of a repository it reads
  local map pair
  local -a pairs
  map="$(env_value HQ_SUBSTITUTE_REPOS)"
  map="${map:-coinepro-hub=/home/Hub/CoinePro-Hub}"
  IFS=',' read -ra pairs <<<"$map"
  for pair in "${pairs[@]}"; do
    if [[ "${pair%%=*}" == "$1" && -d "${pair#*=}" ]]; then
      printf '%s' "${pair#*=}"
      return 0
    fi
  done
  return 1
}

done_with() { # done_with ERROR REASON: a done the dispatcher writes itself
  jq -nc --arg e "$1" --arg r "$2" \
    '{ok: false, text_md: null, findings: null, usage: null, error: $e, limited_until: null,
      status_reason: $r, models: null}' | api "/internal/v1/substitutes/jobs/$id/done" >/dev/null
}

claim="$(printf '' | api /internal/v1/substitutes/jobs/claim)" || exit 0
id="$(jq -r '.job.id // empty' <<<"$claim" 2>/dev/null || true)"
[[ "$id" =~ ^[0-9a-f-]{36}$ ]] || exit 0 # nothing to do (or the holding is locked)

runner=(--profile substitutes run --rm -T)
repo="$(jq -r '.job.checkout.repo // empty' <<<"$claim")"
if [[ -n "$repo" ]]; then
  sha="$(jq -r '.job.checkout.head_sha // empty' <<<"$claim")"
  path="$(repo_path "$repo")" || { done_with no_access "the hub does not read this repository"; exit 0; }
  if [[ ! "$sha" =~ ^[0-9a-f]{7,64}$ ]] || ! git -C "$path" cat-file -e "$sha^{commit}" 2>/dev/null; then
    done_with no_access "the commit is not in the hub's clone"
    exit 0
  fi
  mkdir -m 0755 "$work/checkout"
  (umask 022 && git -C "$path" archive --format=tar "$sha" | tar -x -C "$work/checkout")
  # The secret scan, in the runner's image, as Hub (it owns the copy): every
  # flagged, binary or oversized file and every link removed, whole.
  "$HQ" "${runner[@]}" --user "$(id -u):$(id -g)" --entrypoint python \
    -v "$work/checkout:/checkout" substitute-runner -m hq_common.secret_files /checkout >/dev/null
  chmod -R a-w "$work/checkout"
  runner+=(-v "$work/checkout:/checkout:ro")
fi

login_id="$(jq -r '.job.login.id // empty' <<<"$claim")"
coproc RUN { "$HQ" "${runner[@]}" substitute-runner 2>/dev/null; }
# bash unsets RUN and RUN_PID once the runner exits: kept here.
# shellcheck disable=SC2153 # RUN_PID is set by coproc
run_pid="$RUN_PID" to_run="${RUN[1]}" from_run="${RUN[0]}"
jq -c '{job: .job}' <<<"$claim" >&"$to_run"
finished=0
while IFS= read -r line <&"$from_run"; do
  event="$(jq -r '.event // empty' <<<"$line" 2>/dev/null || true)"
  if [[ "$event" == login_started && "$login_id" =~ ^[0-9a-f-]{36}$ ]]; then
    jq -c '{method, verification_url, user_code}' <<<"$line" |
      api "/internal/v1/substitutes/logins/$login_id/started" >/dev/null
    if [[ "$(jq -r .method <<<"$line")" == auth_code ]]; then
      # The owner's code (write-only in the app) is handed over once, straight
      # into the CLI's terminal; the runner ends the sign-in on its own clock.
      while true; do
        got="$(printf '' | api "/internal/v1/substitutes/logins/$login_id/code")" || got='{}'
        if [[ "$(jq -r '.code // empty' <<<"$got")" != "" ]]; then
          jq -c '{code}' <<<"$got" >&"$to_run"
          break
        fi
        if [[ "$(jq -r '.state // "waiting"' <<<"$got")" != waiting ]]; then
          printf '%s\n' '{"cancel": true}' >&"$to_run"
          break
        fi
        sleep "$CODE_POLL_S"
      done
    fi
  elif [[ "$event" == "done" ]]; then
    jq -c 'del(.event)' <<<"$line" | api "/internal/v1/substitutes/jobs/$id/done" >/dev/null
    finished=1
    break
  fi
done
wait "$run_pid" 2>/dev/null || true
if ((finished == 0)); then done_with failed "the runner stopped without an answer"; fi

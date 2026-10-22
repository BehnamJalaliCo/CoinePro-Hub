#!/usr/bin/env bash
# Tests of infra/substitutes/dispatch.sh (prompt 12 §9.1) with a fake api and
# a fake runner (no docker, no network, no CLI): off by default, nothing while
# the holding is locked, a call's done relayed, the question never on a
# command line, the owner's code relayed once into the sign-in, an unknown
# repository is no_access. Run by scripts/quality/infra.sh.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
failed=0
ok() { echo "test-dispatch: ok: $1"; }
bad() { echo "test-dispatch: FAIL: $1" >&2; failed=1; }

mkdir -p "$T/secrets/substitutes" "$T/run"
printf 'Authorization: Bearer fake\n' >"$T/secrets/substitutes/api-auth"
printf 'HQ_SUBSTITUTES=on\n' >"$T/env"
JOB_ID="0b7a6f2e-0a8e-4a8e-9a43-3a7f1c2d9e10"
LOGIN_ID="1c8b7a3f-1b9f-4b9f-8b54-4b801d3e0f21"
QUESTION="THE-MASKED-QUESTION-42"

cat >"$T/fake-api" <<'EOF'
#!/usr/bin/env bash
# The api's internal routes, as the dispatcher sees them.
body="$(cat)"
printf '%s\t%s\n' "$1" "$body" >>"$FAKE_DIR/api.log"
case "$1" in
  */jobs/claim) cat "$FAKE_DIR/claim.json" ;;
  */code)
    n=$(($(cat "$FAKE_DIR/polls" 2>/dev/null || echo 0) + 1)); echo "$n" >"$FAKE_DIR/polls"
    if ((n < 2)); then echo '{"code": null, "state": "waiting"}'
    else echo '{"code": "GOOD-CODE-123", "state": "waiting"}'; fi ;;
  *) echo '{"state": "ok"}' ;;
esac
EOF
cat >"$T/fake-hq" <<'EOF'
#!/usr/bin/env bash
# hq.sh as the dispatcher calls it: the prune step, or the runner.
printf '%s\n' "$*" >>"$FAKE_DIR/argv.log"
mount=""
prev=""
for a in "$@"; do
  if [[ "$prev" == -v && "$a" == *:/checkout* ]]; then mount="${a%%:/checkout*}"; fi
  prev="$a"
done
case " $* " in
  *" -m hq_common.secret_files "*)
    # The real secret scan on the host copy (the image runs the same module).
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$HQ_COMMON_SRC" python3 -m hq_common.secret_files "$mount" >/dev/null
    exit 0 ;;
esac
if [[ -n "$mount" ]]; then (cd "$mount" && find . -type f | sed 's#^\./##' | sort) >"$FAKE_DIR/listing"; fi
IFS= read -r job
printf '%s\n' "$job" >"$FAKE_DIR/job.json"
case "$(cat "$FAKE_DIR/mode")" in
  call) echo '{"event": "done", "ok": true, "text_md": "answer", "findings": null, "usage": {"input_tokens": 1, "output_tokens": 1, "estimated": true}, "error": null, "limited_until": null, "status_reason": null, "models": null}' ;;
  login)
    echo '{"event": "login_started", "method": "auth_code", "verification_url": "https://accounts.google.com/o/oauth2/v2/auth?x=1", "user_code": null}'
    IFS= read -r code
    printf '%s\n' "$code" >"$FAKE_DIR/code.json"
    echo '{"event": "done", "ok": true, "text_md": null, "findings": null, "usage": null, "error": null, "limited_until": null, "status_reason": null, "models": null}' ;;
  silent) exit 1 ;;
esac
EOF
chmod +x "$T/fake-api" "$T/fake-hq"

run() { # run MODE CLAIM_JSON
  rm -f "$T/api.log" "$T/argv.log" "$T/job.json" "$T/code.json" "$T/polls"
  printf '%s' "$1" >"$T/mode"
  printf '%s' "$2" >"$T/claim.json"
  FAKE_DIR="$T" HQ_SH="$T/fake-hq" HQ_SUBSTITUTE_CURL="$T/fake-api" HQ_ENV_FILE="$T/env" \
    HQ_COMMON_SRC="$HERE/../../services/hq-common/src" \
    HQ_SECRETS_DIR="$T/secrets" RUNTIME_DIRECTORY="$T/run" HQ_SUBSTITUTES="${3:-}" \
    HQ_SUBSTITUTE_CODE_POLL_S="${HQ_SUBSTITUTE_CODE_POLL_S:-0}" \
    bash "$HERE/dispatch.sh"
}
call_job() {
  jq -nc --arg id "$JOB_ID" --arg q "$QUESTION" '{job: {id: $id, kind: "call", player: "gpt",
    runner: "codex_cli", seat: "assistant_errand", model: "gpt-5.5", input_md: $q,
    checkout: null, login: null, timeout_s: 60}}'
}

# Off: nothing at all.
printf 'HQ_SUBSTITUTES=off\n' >"$T/env"
run call "$(call_job)" off
if [[ -e "$T/api.log" || -e "$T/argv.log" ]]; then bad "off still called the api or the runner"; else ok "off by default"; fi
printf 'HQ_SUBSTITUTES=on\n' >"$T/env"

# The holding is locked: the api answers no job, no runner starts.
run call '{"job": null, "skipped": "holding_locked"}'
if [[ -e "$T/argv.log" ]] || [[ "$(cut -f1 "$T/api.log")" != "/internal/v1/substitutes/jobs/claim" ]]; then
  bad "a locked holding still started a runner"
else
  ok "nothing runs while the holding is locked"
fi

# A call: the job on the runner's stdin, done relayed, the question never in argv.
run call "$(call_job)"
done_line="$(grep -F "/jobs/$JOB_ID/done" "$T/api.log" | cut -f2)"
if [[ "$(jq -r .ok <<<"$done_line")" != true || "$(jq -r .text_md <<<"$done_line")" != answer ]]; then
  bad "the call's done was not relayed ($done_line)"
elif jq -e 'has("event")' <<<"$done_line" >/dev/null; then
  bad "the done body still carries its event"
elif grep -qF "$QUESTION" "$T/argv.log"; then
  bad "the question reached a command line"
elif [[ "$(jq -r .job.input_md "$T/job.json")" != "$QUESTION" ]]; then
  bad "the runner did not get the job on its stdin"
else
  ok "a call: job on stdin, done relayed, nothing in argv"
fi

# A sign-in: started relayed, the owner's code polled and handed over once.
login_job="$(jq -nc --arg id "$JOB_ID" --arg l "$LOGIN_ID" '{job: {id: $id, kind: "login",
  player: "gemini", runner: "gemini_cli", seat: null, model: null, input_md: null, checkout: null,
  login: {id: $l, method: "auth_code"}, timeout_s: 600}}')"
HQ_SUBSTITUTE_CODE_POLL_S=0 run login "$login_job"
if ! grep -qF "/logins/$LOGIN_ID/started" "$T/api.log"; then
  bad "login_started was not relayed"
elif [[ "$(jq -r .code "$T/code.json" 2>/dev/null)" != GOOD-CODE-123 ]]; then
  bad "the owner's code did not reach the sign-in"
elif grep -qF GOOD-CODE-123 "$T/argv.log"; then
  bad "the owner's code reached a command line"
elif ! grep -qF "/jobs/$JOB_ID/done" "$T/api.log"; then
  bad "the sign-in's done was not relayed"
else
  ok "a sign-in: started relayed, the code handed over once"
fi

# A code review of a repository the hub does not read: no_access, no runner.
review="$(jq -nc --arg id "$JOB_ID" '{job: {id: $id, kind: "call", player: "gpt", runner: "codex_cli",
  seat: "code_review", model: null, input_md: "review", checkout: {repo: "elsewhere", head_sha: "abcdef1"},
  login: null, timeout_s: 60}}')"
run call "$review"
if [[ -e "$T/argv.log" ]] || [[ "$(grep -F /done "$T/api.log" | cut -f2 | jq -r .error)" != no_access ]]; then
  bad "an unknown repository was not no_access"
else
  ok "an unknown repository is no_access"
fi

# A code review: the hub's clone at head_sha, the secret scan's files gone,
# mounted read-only.
repo="$T/repo"
mkdir -p "$repo/src"
printf 'print("hi")\n' >"$repo/src/app.py"
printf 'ANTHROPIC_API_KEY=sk-ant-api03-%s\n' "$(printf 'D%.0s' $(seq 80))" >"$repo/.env"
git -C "$repo" init -q
git -C "$repo" -c user.email=t@t -c user.name=t add -A
git -C "$repo" -c user.email=t@t -c user.name=t commit -qm one
sha="$(git -C "$repo" rev-parse HEAD)"
printf 'HQ_SUBSTITUTES=on\nHQ_SUBSTITUTE_REPOS=testrepo=%s\n' "$repo" >"$T/env"
review="$(jq -nc --arg id "$JOB_ID" --arg sha "$sha" '{job: {id: $id, kind: "call", player: "gpt",
  runner: "codex_cli", seat: "code_review", model: null, input_md: "review",
  checkout: {repo: "testrepo", head_sha: $sha}, login: null, timeout_s: 60}}')"
run call "$review"
if ! grep -q -- "-v [^ ]*/checkout:/checkout:ro substitute-runner$" "$T/argv.log"; then
  bad "the checkout was not mounted read-only ($(tail -n1 "$T/argv.log"))"
elif [[ "$(cat "$T/listing")" != "src/app.py" ]]; then
  bad "the checkout held more than the clean code: $(tr '\n' ' ' <"$T/listing")"
else
  ok "a code review: the clone at head_sha, .env pruned, read-only"
fi
printf 'HQ_SUBSTITUTES=on\n' >"$T/env"

# A runner that dies without an answer: a failed done all the same.
run silent "$(call_job)"
if [[ "$(grep -F /done "$T/api.log" | cut -f2 | jq -r .error)" != failed ]]; then
  bad "a silent runner left its job without a done"
else
  ok "a silent runner still ends its job (failed)"
fi
exit "$failed"

#!/usr/bin/env bash
# The single entry point to `docker compose` for project coinepro-hq.
# Picks the memory profile (lean/full), loads the profile's limits and the
# secrets file, then passes every argument straight to `docker compose`.
#
# Usage: hq.sh <docker compose args...>     e.g. hq.sh ps
#        hq.sh --print-profile
#        hq.sh --print-substitutes-runner   (on|off: what the api is told)
#        hq.sh --print-media                (on|off: the render worker, prompt 13)
#        hq.sh --print-ocr                  (on|off: the archive's OCR, prompt 14)
# Env:   HQ_PROFILE=lean|full   force a profile (else .env, else server RAM)
#        HQ_ENV_FILE=PATH       use another secrets file (CI uses a throwaway one)
#        HQ_ALL_PROFILES=1      act on the services of every profile (used by `down`)
#        HQ_STT=on|off          speech to text (opt-in profile "stt"; else .env)
#        HQ_PROVISIONING=on|off the provisioner (opt-in profile "provisioning"; else .env)
#        HQ_MCP=on|off          MCP servers in containers (opt-in profile "mcp"; else .env)
#        HQ_MEDIA=on|off        the media render worker (opt-in profile "media"; else .env)
#        HQ_OCR=on|off          the archive's OCR (opt-in profile "ocr"; else .env)
set -euo pipefail

COMPOSE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${HQ_ENV_FILE:-$COMPOSE_DIR/.env}"
# The full profile is sized for the hub's 16 GB class (prompt 05 §11); a
# nominal 16 GB server reports a little less (kernel reserve), so the
# threshold is 15 GiB of MemTotal. Anything smaller runs lean. The full
# profile's memory budget is sized for exactly this threshold
# (profiles/full.env HQ_BUDGET_REF_RAM_MB; scripts/quality/memory-budget.sh).
FULL_PROFILE_MIN_MB=15360
FULL_PROFILE_MIN_KB=$((FULL_PROFILE_MIN_MB * 1024))

detect_profile() {
  local p="${HQ_PROFILE:-}"
  if [[ -z "$p" && -r "$ENV_FILE" ]]; then
    p="$(sed -n 's/^HQ_PROFILE=//p' "$ENV_FILE" | tail -n1)"
  fi
  if [[ -z "$p" ]]; then
    local mem_kb
    mem_kb="$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)"
    if ((mem_kb < FULL_PROFILE_MIN_KB)); then p=lean; else p=full; fi
  fi
  case "$p" in
    lean | full) printf '%s\n' "$p" ;;
    *) echo "error: HQ_PROFILE must be lean or full (got '$p')" >&2; return 2 ;;
  esac
}

profile="$(detect_profile)"
if [[ "${1:-}" == "--print-profile" ]]; then
  printf '%s\n' "$profile"
  exit 0
fi

if [[ ! -r "$ENV_FILE" ]]; then
  echo "error: $ENV_FILE not found; run 'make env' first" >&2
  exit 1
fi

export HQ_PROFILE="$profile"
# Single source for the OPA image (also used by test-env and the opa gate).
OPA_IMAGE="$(cat "$COMPOSE_DIR/../opa/IMAGE")"
export OPA_IMAGE

# The public API and passkey login exist only with a real domain over HTTPS
# (contract §2): HQ_SITE_ADDRESS=<domain> switches on /api at the edge and
# gives the api its origin and WebAuthn RP id. Without it /api answers 404.
site="${HQ_SITE_ADDRESS:-$(sed -n 's/^HQ_SITE_ADDRESS=//p' "$ENV_FILE" | tail -n1)}"
# A domain: dot-separated labels whose last label has a letter (an IP address
# is not a domain) and is not "localhost" (no public certificate exists).
tld="${site##*.}"
if [[ "$site" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$ &&
  "$tld" =~ [a-z] && "$tld" != localhost ]]; then
  export HQ_API_EDGE=on HQ_PUBLIC_ORIGIN="https://$site" HQ_WEBAUTHN_RP_ID="$site"
else
  export HQ_API_EDGE=off HQ_PUBLIC_ORIGIN="" HQ_WEBAUTHN_RP_ID=""
fi
# The hub's own addresses (prompt 7.1): egress refuses the hub's /internal by
# them as by its name, and a name that resolves to one of them. The host's
# global addresses and what its domain resolves to (a private one among them
# is refused by egress anyway). Read only; nothing on the host changes.
hub_addresses() {
  {
    ip -o addr show scope global 2>/dev/null | awk '{ split($4, a, "/"); print a[1] }'
    if [[ "$HQ_WEBAUTHN_RP_ID" == *.* ]]; then
      getent ahosts "$HQ_WEBAUTHN_RP_ID" 2>/dev/null | awk '{ print $1 }'
    fi
  } | sort -u | paste -sd, -
}
HQ_HUB_ADDRESSES="${HQ_HUB_ADDRESSES:-$(hub_addresses || true)}"
export HQ_HUB_ADDRESSES
# The web panel (prompt 05 §10) runs once apps/web/Dockerfile exists: profile
# "web", and Caddy sends every path but /api to it (HQ_WEB).
profile_args=(--profile "$profile")
if [[ -f "$COMPOSE_DIR/../../apps/web/Dockerfile" ]]; then
  export HQ_WEB=on
  profile_args+=(--profile web)
else
  export HQ_WEB=off
fi
# The site-check canary (prompt 05 §9.1): Caddy's /__canary fails on purpose
# (503) only while a canary row of the sites seed is enabled; switched off it
# answers 404 like any unknown path (prompt 05.1 §3). The seed keeps each row
# on one line, so a canary row is enabled unless it says `enabled: false`.
SITES_SEED="${HQ_SITES_SEED:-$COMPOSE_DIR/../../apps/api/seed/sites.yaml}"  # override: tests only
export HQ_CANARY=off
if [[ -r "$SITES_SEED" ]] &&
  grep -E '^[[:space:]]*-.*[{,[:space:]]canary:[[:space:]]*true' "$SITES_SEED" |
  grep -qvE '[{,[:space:]]enabled:[[:space:]]*false'; then
  export HQ_CANARY=on
fi
compose() {
  docker compose \
    --project-name coinepro-hq \
    --project-directory "$COMPOSE_DIR" \
    --file "$COMPOSE_DIR/compose.yaml" \
    --file "$COMPOSE_DIR/mcp.yaml" \
    --env-file "$COMPOSE_DIR/profiles/$profile.env" \
    --env-file "$ENV_FILE" \
    "$@"
}

# The compose subcommand: the first argument that is not a global option.
subcommand() {
  while (($#)); do
    case "$1" in
      --ansi | --env-file | -f | --file | --parallel | --profile | --progress | \
        --project-directory | -p | --project-name) shift 2 ;;
      -*) shift ;;
      *) printf '%s\n' "$1"; return ;;
    esac
  done
}

# Speech to text (prompt 06 §3): opt-in profile "stt", switched on with
# HQ_STT=on (.env). While the active profile plus stt is over the memory budget
# (80% of the profile's reference RAM, as the memory gate counts it) it can
# never be switched on by accident: a command that starts or creates
# containers is refused; any other (exec for the backup and unseal, ps, logs,
# config) runs without stt. The worker gets STT_URL only while stt is on.
stt="${HQ_STT:-$(sed -n 's/^HQ_STT=//p' "$ENV_FILE" | tail -n1)}"
export STT_URL=""
if [[ "$stt" == on && "${HQ_ALL_PROFILES:-0}" != "1" ]]; then
  ref="$(sed -n 's/^HQ_BUDGET_REF_RAM_MB=//p' "$COMPOSE_DIR/profiles/$profile.env")"
  # backup-tools (its own profile, run hourly by infra/backup) counts too.
  sum="$(compose "${profile_args[@]}" --profile stt --profile backup-tools config --format json |
    jq '[.services[].deploy.resources.limits.memory | tonumber] | add / 1048576 | floor')"
  budget=$((ref * 80 / 100))
  if ((sum <= budget)); then
    profile_args+=(--profile stt)
    export STT_URL="http://stt:8000"
  else
    over="the $profile profile plus stt needs $sum MiB of memory limits, $((sum - budget)) MiB"
    over+=" over the budget of $budget MiB (80% of $ref MiB)"
    case "$(subcommand "$@")" in
      up | run | create | start | restart)
        echo "error: HQ_STT=on refused: $over." >&2
        echo "       Turning stt on is the owner's decision: the options (a smaller model," \
          "lower limits elsewhere, a bigger server) are in docs/ops/RUNBOOK.md (STT)." >&2
        echo "       Set HQ_STT=off in $ENV_FILE to start the stack without it." >&2
        exit 3
        ;;
      *) echo "warning: HQ_STT=on ignored ($over; docs/ops/RUNBOOK.md, STT)" >&2 ;;
    esac
  fi
fi
# The provisioner (prompt 09 §4): opt-in profile "provisioning", switched on
# with HQ_PROVISIONING=on (.env) once the owner has stored the Hetzner token
# (make hetzner-token). The same memory rule as stt; the api gets
# PROVISIONER_URL only while it is on.
provisioning="${HQ_PROVISIONING:-$(sed -n 's/^HQ_PROVISIONING=//p' "$ENV_FILE" | tail -n1)}"
export PROVISIONER_URL=""
if [[ "$provisioning" == on && "${HQ_ALL_PROFILES:-0}" != "1" ]]; then
  ref="$(sed -n 's/^HQ_BUDGET_REF_RAM_MB=//p' "$COMPOSE_DIR/profiles/$profile.env")"
  sum="$(compose "${profile_args[@]}" --profile provisioning config --format json |
    jq '[.services[].deploy.resources.limits.memory | tonumber] | add / 1048576 | floor')"
  budget=$((ref * 80 / 100))
  if ((sum <= budget)); then
    profile_args+=(--profile provisioning)
    export PROVISIONER_URL="http://provisioner:8110"
  else
    over="the $profile profile plus the provisioner needs $sum MiB of memory limits,"
    over+=" $((sum - budget)) MiB over the budget of $budget MiB (80% of $ref MiB)"
    case "$(subcommand "$@")" in
      up | run | create | start | restart)
        echo "error: HQ_PROVISIONING=on refused: $over." >&2
        echo "       Set HQ_PROVISIONING=off in $ENV_FILE to start the stack without it." >&2
        exit 3
        ;;
      *) echo "warning: HQ_PROVISIONING=on ignored ($over)" >&2 ;;
    esac
  fi
fi
# Tracing (review 7.1 §0.2): opt-in profile "tracing" (Tempo + otel-collector),
# off by default, switched on with HQ_TRACING=on (.env; `make tracing-on`),
# refused like stt while it does not fit the memory budget. Prometheus scrapes
# the two only while it is on (HQ_TRACING_SCRAPE).
tracing="${HQ_TRACING:-$(sed -n 's/^HQ_TRACING=//p' "$ENV_FILE" | tail -n1)}"
export HQ_TRACING_SCRAPE=off
if [[ "$tracing" == on && "${HQ_ALL_PROFILES:-0}" != "1" ]]; then
  ref="$(sed -n 's/^HQ_BUDGET_REF_RAM_MB=//p' "$COMPOSE_DIR/profiles/$profile.env")"
  sum="$(compose "${profile_args[@]}" --profile tracing config --format json |
    jq '[.services[].deploy.resources.limits.memory | tonumber] | add / 1048576 | floor')"
  budget=$((ref * 80 / 100))
  if ((sum <= budget)); then
    profile_args+=(--profile tracing)
    export HQ_TRACING_SCRAPE=on
  else
    over="the $profile profile plus tracing needs $sum MiB of memory limits, $((sum - budget)) MiB"
    over+=" over the budget of $budget MiB (80% of $ref MiB)"
    case "$(subcommand "$@")" in
      up | run | create | start | restart)
        echo "error: HQ_TRACING=on refused: $over (make tracing-off)." >&2
        exit 3
        ;;
      *) echo "warning: HQ_TRACING=on ignored ($over)" >&2 ;;
    esac
  fi
fi
# MCP servers in containers (prompt 12 §14): opt-in profile "mcp"
# (infra/compose/mcp.yaml), off by default, switched on with HQ_MCP=on (.env)
# and refused like stt while it does not fit the memory budget. The api gets
# MCP_CONTAINERS=on only while it is on (else a container server's enable
# answers 409 not_ready and mcp.call channel_not_configured).
mcp="${HQ_MCP:-$(sed -n 's/^HQ_MCP=//p' "$ENV_FILE" | tail -n1)}"
export MCP_CONTAINERS=off
if [[ "$mcp" == on && "${HQ_ALL_PROFILES:-0}" != "1" ]]; then
  ref="$(sed -n 's/^HQ_BUDGET_REF_RAM_MB=//p' "$COMPOSE_DIR/profiles/$profile.env")"
  sum="$(compose "${profile_args[@]}" --profile mcp --profile backup-tools config --format json |
    jq '[.services[].deploy.resources.limits.memory | tonumber] | add / 1048576 | floor')"
  budget=$((ref * 80 / 100))
  if ((sum <= budget)); then
    profile_args+=(--profile mcp)
    export MCP_CONTAINERS=on
  else
    over="the $profile profile plus mcp needs $sum MiB of memory limits, $((sum - budget)) MiB"
    over+=" over the budget of $budget MiB (80% of $ref MiB)"
    case "$(subcommand "$@")" in
      up | run | create | start | restart)
        echo "error: HQ_MCP=on refused: $over." >&2
        echo "       Turning mcp on is the owner's decision (docs/ops/RUNBOOK.md, MCP in containers)." >&2
        echo "       Set HQ_MCP=off in $ENV_FILE to start the stack without it." >&2
        exit 3
        ;;
      *) echo "warning: HQ_MCP=on ignored ($over)" >&2 ;;
    esac
  fi
fi
# The substitute players (prompt 12 §9.1): opt-in profiles "substitutes" (the
# one-shot CLI runner) and "substitutes-web" (the signed-in browser profiles),
# off by default (HQ_SUBSTITUTES / HQ_SUBSTITUTES_WEB=on in .env), each refused
# like stt while the profile plus it does not fit the memory budget. The api
# gets SUBSTITUTES_RUNNER=on only while the runner is on (its CLI sign-in from
# the app answers 409 not_ready otherwise).
export SUBSTITUTES_RUNNER=off
for opt in substitutes substitutes-web; do
  var="HQ_$(tr '[:lower:]-' '[:upper:]_' <<<"$opt")"
  value="${!var:-$(sed -n "s/^$var=//p" "$ENV_FILE" | tail -n1)}"
  [[ "$value" == on && "${HQ_ALL_PROFILES:-0}" != "1" ]] || continue
  ref="$(sed -n 's/^HQ_BUDGET_REF_RAM_MB=//p' "$COMPOSE_DIR/profiles/$profile.env")"
  sum="$(compose "${profile_args[@]}" --profile "$opt" --profile backup-tools config --format json |
    jq '[.services[].deploy.resources.limits.memory | tonumber] | add / 1048576 | floor')"
  budget=$((ref * 80 / 100))
  if ((sum <= budget)); then
    profile_args+=(--profile "$opt")
    if [[ "$opt" == substitutes ]]; then export SUBSTITUTES_RUNNER=on; fi
  else
    over="the $profile profile plus $opt needs $sum MiB of memory limits, $((sum - budget)) MiB"
    over+=" over the budget of $budget MiB (80% of $ref MiB)"
    case "$(subcommand "$@")" in
      up | run | create | start | restart)
        echo "error: $var=on refused: $over." >&2
        echo "       Turning it on is the owner's decision (STT, TTS, container MCP and the" \
          "substitute players share the room; docs/ops/RUNBOOK.md)." >&2
        echo "       Set $var=off in $ENV_FILE to start the stack without it." >&2
        exit 3
        ;;
      *) echo "warning: $var=on ignored ($over)" >&2 ;;
    esac
  fi
done
if [[ "${1:-}" == "--print-substitutes-runner" ]]; then # the quality gate's check
  printf '%s\n' "$SUBSTITUTES_RUNNER"
  exit 0
fi
# The Persian voice (prompt 12 §4): opt-in profile "tts", switched on with
# HQ_TTS=on (.env; `make tts-on`), a one-shot run by the coinepro-hq-tts timer.
# Refused like stt while the profile plus tts does not fit the memory budget;
# the api queues audio only while it is on (HQ_TTS_ACTIVE). Off by default:
# STT, TTS, container MCP and the substitutes' runner wait for the owner's
# order of memory (prompt 12 §0.8 #7).
tts="${HQ_TTS:-$(sed -n 's/^HQ_TTS=//p' "$ENV_FILE" | tail -n1)}"
export HQ_TTS_ACTIVE=off
if [[ "$tts" == on && "${HQ_ALL_PROFILES:-0}" != "1" ]]; then
  ref="$(sed -n 's/^HQ_BUDGET_REF_RAM_MB=//p' "$COMPOSE_DIR/profiles/$profile.env")"
  sum="$(compose "${profile_args[@]}" --profile tts --profile backup-tools config --format json |
    jq '[.services[].deploy.resources.limits.memory | tonumber] | add / 1048576 | floor')"
  budget=$((ref * 80 / 100))
  if ((sum <= budget)); then
    profile_args+=(--profile tts)
    export HQ_TTS_ACTIVE=on
  else
    over="the $profile profile plus tts needs $sum MiB of memory limits, $((sum - budget)) MiB"
    over+=" over the budget of $budget MiB (80% of $ref MiB)"
    case "$(subcommand "$@")" in
      up | run | create | start | restart)
        echo "error: HQ_TTS=on refused: $over (make tts-off)." >&2
        exit 3
        ;;
      *) echo "warning: HQ_TTS=on ignored ($over)" >&2 ;;
    esac
  fi
fi
# The media studio's render worker (prompt 13 §2.3): opt-in profile "media"
# (the courier and the network-less renderer, one-shots run by the
# coinepro-hq-media timer), switched on with HQ_MEDIA=on (.env; `make
# media-on`). Refused like stt while the profile plus media does not fit the
# memory budget; the api queues renders only while it is on (HQ_MEDIA_ACTIVE).
# Off by default: the opt-ins share the room and wait for the owner's order.
media="${HQ_MEDIA:-$(sed -n 's/^HQ_MEDIA=//p' "$ENV_FILE" | tail -n1)}"
export HQ_MEDIA_ACTIVE=off
if [[ "$media" == on && "${HQ_ALL_PROFILES:-0}" != "1" ]]; then
  ref="$(sed -n 's/^HQ_BUDGET_REF_RAM_MB=//p' "$COMPOSE_DIR/profiles/$profile.env")"
  sum="$(compose "${profile_args[@]}" --profile media --profile backup-tools config --format json |
    jq '[.services[].deploy.resources.limits.memory | tonumber] | add / 1048576 | floor')"
  budget=$((ref * 80 / 100))
  if ((sum <= budget)); then
    profile_args+=(--profile media)
    export HQ_MEDIA_ACTIVE=on
  else
    over="the $profile profile plus media needs $sum MiB of memory limits, $((sum - budget)) MiB"
    over+=" over the budget of $budget MiB (80% of $ref MiB)"
    case "$(subcommand "$@")" in
      up | run | create | start | restart)
        echo "error: HQ_MEDIA=on refused: $over (make media-off)." >&2
        exit 3
        ;;
      *) echo "warning: HQ_MEDIA=on ignored ($over)" >&2 ;;
    esac
  fi
fi
if [[ "${1:-}" == "--print-media" ]]; then # the quality gate's check
  printf '%s\n' "$HQ_MEDIA_ACTIVE"
  exit 0
fi
# The archive's OCR (prompt 14 §4): opt-in profile "ocr" (Tesseract on the
# internal hq-ocr, the worker its only client), switched on with HQ_OCR=on
# (.env; `make ocr-on`, after `make ocr-fetch`). Refused like stt while the
# profile plus ocr does not fit the memory budget; the worker gets HQ_OCR_URL
# only while it is on (else scanned files keep text_state "none").
ocr="${HQ_OCR:-$(sed -n 's/^HQ_OCR=//p' "$ENV_FILE" | tail -n1)}"
export HQ_OCR_URL=""
if [[ "$ocr" == on && "${HQ_ALL_PROFILES:-0}" != "1" ]]; then
  ref="$(sed -n 's/^HQ_BUDGET_REF_RAM_MB=//p' "$COMPOSE_DIR/profiles/$profile.env")"
  sum="$(compose "${profile_args[@]}" --profile ocr --profile backup-tools config --format json |
    jq '[.services[].deploy.resources.limits.memory | tonumber] | add / 1048576 | floor')"
  budget=$((ref * 80 / 100))
  if ((sum <= budget)); then
    profile_args+=(--profile ocr)
    export HQ_OCR_URL="http://ocr:8088"
  else
    over="the $profile profile plus ocr needs $sum MiB of memory limits, $((sum - budget)) MiB"
    over+=" over the budget of $budget MiB (80% of $ref MiB)"
    case "$(subcommand "$@")" in
      up | run | create | start | restart)
        echo "error: HQ_OCR=on refused: $over (make ocr-off)." >&2
        exit 3
        ;;
      *) echo "warning: HQ_OCR=on ignored ($over)" >&2 ;;
    esac
  fi
fi
if [[ "${1:-}" == "--print-ocr" ]]; then # the quality gate's check
  if [[ -n "$HQ_OCR_URL" ]]; then echo on; else echo off; fi
  exit 0
fi
if [[ "${HQ_ALL_PROFILES:-0}" == "1" ]]; then
  profile_args=(--profile "*")
fi

compose "${profile_args[@]}" "$@"

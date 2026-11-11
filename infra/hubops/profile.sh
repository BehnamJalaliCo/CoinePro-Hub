#!/usr/bin/env bash
# One optional service on or off for hub.ops `profile` and the owner's «سرویس‌ها» page (contract
# §38.1, §38.3), through the repository's own make targets. Run by the hub-ops dispatcher as user Hub
# without sudo (HQ_NO_SUDO=1: the timers those targets enable were enabled once by
# `make hubops-install`, and each one-shot does nothing while its switch is off).
#   profile.sh NAME on|off [TURN_OFF...]
# Before switching on, the memory budget is asked first (hq.sh `config` with NAME's switch on and
# each TURN_OFF switch off): over it the answer is exit 3 with hq.sh's own words, and nothing
# changed (no target ran, every switch in .env as it was). Only then are TURN_OFF (other optional
# services) switched off, and NAME on. A target that fails leaves NAME's switch off again.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HQ="${HQ_SH:-$REPO_DIR/infra/compose/hq.sh}"
SET_ENV="${HQ_SET_ENV:-$REPO_DIR/infra/compose/set-env.sh}"
MAKE_BIN="${HQ_MAKE:-make}"

spec() { # spec NAME -> "VAR ON_TARGET OFF_TARGET"
  case "$1" in
    media) echo "HQ_MEDIA media-on media-off" ;;
    tts) echo "HQ_TTS tts-on tts-off" ;;
    stt) echo "HQ_STT stt-on stt-off" ;;
    ocr) echo "HQ_OCR ocr-on ocr-off" ;;
    newsletter) echo "HQ_NEWSLETTER newsletter-on newsletter-off" ;;
    automations) echo "HQ_AUTOMATIONS n8n-on n8n-off" ;;
    tracing) echo "HQ_TRACING tracing-on tracing-off" ;;
    *) return 1 ;;
  esac
}
target() { "$MAKE_BIN" -C "$REPO_DIR" "$1" HQ_NO_SUDO=1; }

name="${1:-}" want="${2:-}"
shift 2 || { echo "usage: profile.sh NAME on|off [TURN_OFF...]" >&2; exit 2; }
s="$(spec "$name")" || { echo "profile: unknown service: $name" >&2; exit 2; }
read -r var on_t off_t <<<"$s"
[[ "$want" == on || "$want" == off ]] || { echo "profile: on or off" >&2; exit 2; }
for k in "$@"; do
  spec "$k" >/dev/null && [[ "$k" != "$name" ]] || { echo "profile: cannot turn off: $k" >&2; exit 2; }
done

turn_off() {
  local k k_off
  for k in "$@"; do
    read -r _ _ k_off <<<"$(spec "$k")"
    echo "profile: switching $k off first"
    target "$k_off"
  done
}

if [[ "$want" == off ]]; then
  turn_off "$@"
  target "$off_t"
  echo "profile: $name is off"
  exit 0
fi

# Does it fit, with the TURN_OFF services counted off? Asked before any target runs, so a refusal
# changes nothing. hq.sh reads each switch from the environment before .env, and answers `config`
# with a warning, and starts nothing, when it does not fit.
check_env=("$var=on")
for k in "$@"; do
  read -r k_var _ _ <<<"$(spec "$k")"
  check_env+=("$k_var=off")
done
over="$(env "${check_env[@]}" "$HQ" config --quiet 2>&1 >/dev/null | grep -F "$var=on ignored" || true)"
if [[ -n "$over" ]]; then
  printf '%s\n' "$over"
  echo "profile: $name refused: over the memory budget (nothing changed)"
  exit 3
fi
turn_off "$@"
if ! target "$on_t"; then
  "$SET_ENV" "$var" off >/dev/null 2>&1 || true
  echo "profile: $name did not start; its switch is off again" >&2
  exit 1
fi
echo "profile: $name is on"

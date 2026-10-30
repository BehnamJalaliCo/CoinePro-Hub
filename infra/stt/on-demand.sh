#!/usr/bin/env bash
# Speech to text on demand (⟨1.9⟩ prompt 18, contract §27.3). The worker
# touches /run/hq/stt/want before every piece of audio it transcribes; the
# host's coinepro-hq-stt.path then runs this (coinepro-hq-stt.service, as
# user Hub). Nothing unless HQ_STT=on (.env; `make stt-on`).
#   1. take /run/hq/oneshot.lock (the hourly backup, the TTS and the render
#      passes hold it too: the memory gate counts stt as a burst beside them,
#      never on top of the backup's one-shot);
#   2. start stt (hq.sh with HQ_STT_START=1; refused over the memory budget);
#   3. keep it up while transcriptions come: started again if it stopped
#      (a crash) while the worker still asks;
#   4. stop it STT_IDLE_STOP_S (300) after the last request, or after
#      STT_MAX_HOLD_S (600) in a row so a waiting backup (15 minutes at
#      most) always gets the lock; the next request starts it again.
# The worker has no Docker socket: only this file, which it can touch.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${HQ_ENV_FILE:-$REPO_DIR/infra/compose/.env}"
HQ="${HQ_SH:-$REPO_DIR/infra/compose/hq.sh}"
LOCK="${HQ_ONESHOT_LOCK:-/run/hq/oneshot.lock}"
WANT="${HQ_STT_WANT:-/run/hq/stt/want}"
IDLE_S="${STT_IDLE_STOP_S:-300}"
MAX_HOLD_S="${STT_MAX_HOLD_S:-600}"
POLL_S="${STT_POLL_S:-5}"

stt="${HQ_STT:-$(sed -n 's/^HQ_STT=//p' "$ENV_FILE" 2>/dev/null | tail -n1)}"
if [[ "$stt" != on ]]; then
  exit 0
fi
last_want() { stat -c %Y "$WANT" 2>/dev/null || echo 0; }
if (($(date +%s) - $(last_want) >= IDLE_S)); then
  exit 0 # an old touch (a reboot, a stale path event): nobody is waiting
fi
if [[ ! -d "$(dirname "$LOCK")" ]]; then
  echo "stt: $(dirname "$LOCK") is missing (infra/systemd/install.sh creates it)" >&2
  exit 1
fi
exec 9>"$LOCK"
if ! flock -w 600 9; then
  echo "stt: the one-shot lock stayed busy for 10 minutes; the worker asks again"
  exit 0
fi

running() { [[ -n "$(HQ_STT_START=1 "$HQ" ps --status running -q stt 2>/dev/null)" ]]; }
start() { HQ_STT_START=1 "$HQ" up -d --no-deps stt >/dev/null; }

begun="$(date +%s)"
t0="$(date +%s%N)"
start
echo "stt: started on demand ($((($(date +%s%N) - t0) / 1000000)) ms to start the container)"
reason=idle
while :; do
  sleep "$POLL_S"
  now="$(date +%s)"
  if ((now - $(last_want) >= IDLE_S)); then
    reason=idle
    break
  fi
  if ((now - begun >= MAX_HOLD_S)); then
    reason="held ${MAX_HOLD_S} s (the lock goes to a waiting one-shot)"
    break
  fi
  if ! running; then
    echo "stt: not running while asked for; starting it again" >&2
    start
  fi
done
HQ_STT_START=1 "$HQ" stop -t 10 stt >/dev/null
echo "stt: stopped ($reason)"

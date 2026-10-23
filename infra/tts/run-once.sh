#!/usr/bin/env bash
# One pass of the Persian voice (prompt 12 §4): the coinepro-hq-tts timer runs
# it every 2 minutes. Nothing unless HQ_TTS=on (.env). It waits up to 10
# minutes on /run/hq/oneshot.lock, which the hourly backup holds while it runs
# (the one-shots never overlap: the memory gate counts them once), then runs
# the tts one-shot. The one-shot asks the api for work: 204 while there is
# none, and always while the holding is locked (nothing is spoken then).
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${HQ_ENV_FILE:-$REPO_DIR/infra/compose/.env}"
LOCK="${HQ_ONESHOT_LOCK:-/run/hq/oneshot.lock}"

tts="${HQ_TTS:-$(sed -n 's/^HQ_TTS=//p' "$ENV_FILE" 2>/dev/null | tail -n1)}"
if [[ "$tts" != on ]]; then
  exit 0
fi
if [[ ! -d "$(dirname "$LOCK")" ]]; then
  echo "tts: $(dirname "$LOCK") is missing (infra/systemd/install.sh creates it)" >&2
  exit 1
fi
exec 9>"$LOCK"
if ! flock -w 600 9; then
  echo "tts: the one-shot lock stayed busy for 10 minutes; the next pass tries again"
  exit 0
fi
"$REPO_DIR/infra/compose/hq.sh" run --rm --no-deps tts

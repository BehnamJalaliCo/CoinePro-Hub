#!/usr/bin/env bash
# One render pass of the media studio (prompt 13 §2.3, contract §22.2 step 6):
# the coinepro-hq-media timer runs it every 2 minutes. Nothing unless
# HQ_MEDIA=on (.env). It waits up to 10 minutes on /run/hq/oneshot.lock (the
# hourly backup and the TTS pass hold it too: the one-shots never overlap),
# then, for at most MEDIA_MAX_JOBS jobs:
#   1. media-courier claim   (hq-media: the api and OpenBao only) -> a job id,
#      or nothing: no job, and always while the holding or the job's company
#      is locked (the api answers 204, so nothing is rendered then);
#   2. media-render render   (NO network at all) under a hard deadline: the
#      job's own limit inside, and this script kills the container a minute
#      after MEDIA_TIMEOUT_S;
#   3. media-courier send    the outputs (or the failure) back; the job's
#      folder in the volume is removed.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${HQ_ENV_FILE:-$REPO_DIR/infra/compose/.env}"
LOCK="${HQ_ONESHOT_LOCK:-/run/hq/oneshot.lock}"
HQ="$REPO_DIR/infra/compose/hq.sh"
MAX_JOBS="${MEDIA_MAX_JOBS:-2}"
TIMEOUT_S="${MEDIA_TIMEOUT_S:-600}"

media="${HQ_MEDIA:-$(sed -n 's/^HQ_MEDIA=//p' "$ENV_FILE" 2>/dev/null | tail -n1)}"
if [[ "$media" != on ]]; then
  exit 0
fi
if [[ ! -d "$(dirname "$LOCK")" ]]; then
  echo "media: $(dirname "$LOCK") is missing (infra/systemd/install.sh creates it)" >&2
  exit 1
fi
exec 9>"$LOCK"
if ! flock -w 600 9; then
  echo "media: the one-shot lock stayed busy for 10 minutes; the next pass tries again"
  exit 0
fi

for _ in $(seq "$MAX_JOBS"); do
  job="$("$HQ" run --rm --no-deps -T media-courier courier claim)"
  if [[ -z "$job" ]]; then
    break # nothing to render (also while the holding is locked)
  fi
  if [[ ! "$job" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]]; then
    echo "media: the courier's answer is not a job id; stopping this pass" >&2
    exit 1
  fi
  name="hq-media-render-${job:0:8}"
  rc=0
  timeout --kill-after=30 "$((TIMEOUT_S + 60))" \
    "$HQ" run --rm --no-deps -T --name "$name" media-render render "$job" || rc=$?
  if ((rc != 0)); then
    # The deadline passed or the container was killed (memory): make sure it is
    # gone; the courier reports the job as failed (no manifest: render_killed).
    docker rm -f "$name" >/dev/null 2>&1 || true
    echo "media: the render of $job stopped (status $rc)" >&2
  fi
  "$HQ" run --rm --no-deps -T media-courier courier send "$job"
done

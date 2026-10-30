#!/usr/bin/env bash
# `make stt-cold`: stt's cold start on this server, as the worker meets it:
# stopped -> the container started -> /health answers -> the first
# transcription of a 1-second tone (the model loads on it). Under the
# one-shot lock, like the starter; stt is stopped again afterwards unless
# it was already running. Prints milliseconds only.
set -euo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HQ="$REPO_DIR/infra/compose/hq.sh"
LOCK="${HQ_ONESHOT_LOCK:-/run/hq/oneshot.lock}"
ms() { echo $((($(date +%s%N) - $1) / 1000000)); }
exec 9>"$LOCK"
flock -w 600 9 || { echo "stt-cold: the one-shot lock stayed busy" >&2; exit 1; }
if [[ -n "$(HQ_STT_START=1 "$HQ" ps --status running -q stt 2>/dev/null)" ]]; then
  echo "stt-cold: stt is running (a transcription is on); try again in 5 minutes" >&2
  exit 1
fi
t0="$(date +%s%N)"
HQ_STT_START=1 "$HQ" up -d --no-deps stt >/dev/null
echo "container started: $(ms "$t0") ms"
until HQ_STT_START=1 "$HQ" exec -T stt python -c \
  "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/health', timeout=2)" >/dev/null 2>&1; do
  sleep 0.2
done
echo "health answers:    $(ms "$t0") ms"
HQ_STT_START=1 "$HQ" exec -T stt python -c '
import io, math, struct, urllib.request as u, wave
b = io.BytesIO(); w = wave.open(b, "wb"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 300 * i / 16000))) for i in range(16000))); w.close()
r = u.Request("http://127.0.0.1:8000/v1/transcribe", data=b.getvalue(), headers={"Content-Type": "audio/wav"})
u.urlopen(r, timeout=120).read()' >/dev/null
echo "first transcript:  $(ms "$t0") ms (the model loaded on it)"
HQ_STT_START=1 "$HQ" stop -t 10 stt >/dev/null

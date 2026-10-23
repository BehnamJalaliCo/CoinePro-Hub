# tts: the hub's Persian voice (prompt 12 §4, contract §21.4). A one-shot, not
# a service: the timer coinepro-hq-tts runs it (infra/tts/run-once.sh) under the
# one-shot lock; it claims a briefing's spoken script from the api, makes the
# voice with Piper on the CPU (no audio ever leaves the hub), encodes it as
# Ogg/Opus 32 kbps with opusenc and sends it back. The voice is pinned by hash
# (voice.lock.json: rhasspy/piper-voices at a fixed revision).
# Runs as uid 10001 on a read-only root filesystem (compose adds the tmpfs).
FROM python:3.12.15-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/hq-common/src:/app/tts/src \
    HOME=/tmp/home \
    OMP_NUM_THREADS=2 \
    TTS_VOICES_DIR=/voices

# opusenc (opus-tools, BSD; libopus, BSD-3; Debian trixie, exact version): WAV
# to Ogg/Opus. Six small packages instead of ffmpeg's 205 (about 1 GB less disk).
RUN apt-get update \
    && apt-get install -y --no-install-recommends opus-tools=0.2-1+b3 \
    && rm -rf /var/lib/apt/lists/*

COPY tts/requirements.lock /tmp/requirements.lock
RUN pip install --require-hashes --no-deps -r /tmp/requirements.lock \
    && rm /tmp/requirements.lock \
    && useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin hq

# The voice (dataset CC0-1.0 per its MODEL_CARD; weights MIT), checked by sha256.
ADD --chmod=644 --checksum=sha256:fb815380d969ea372b0b21b0de14421f58fe481047e153e69685d079b6e1a9d1 \
    https://huggingface.co/rhasspy/piper-voices/resolve/5041a7a49ae5b3a0f30e6837769eb03fdbb231bd/fa/fa_IR/amir/medium/fa_IR-amir-medium.onnx \
    /voices/fa_IR-amir-medium.onnx
ADD --chmod=644 --checksum=sha256:75f918a3bf0f57a9179abe725af529f2a5c79d6c899e2a84aec76c685d5dfb9a \
    https://huggingface.co/rhasspy/piper-voices/resolve/5041a7a49ae5b3a0f30e6837769eb03fdbb231bd/fa/fa_IR/amir/medium/fa_IR-amir-medium.onnx.json \
    /voices/fa_IR-amir-medium.onnx.json
RUN chmod 0755 /voices

COPY hq-common/src /app/hq-common/src
COPY tts/voice.lock.json /app/tts/voice.lock.json
COPY tts/src /app/tts/src

USER 10001
WORKDIR /app/tts
CMD ["python", "-m", "hq_tts"]

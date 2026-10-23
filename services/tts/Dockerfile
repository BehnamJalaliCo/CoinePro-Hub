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
# Prompt 13 §4: the other Persian Piper voices of the same revision for the
# bake-off (datasets CC0-1.0 per their MODEL_CARDs; weights MIT), each by sha256.
ADD --chmod=644 --checksum=sha256:6a98504bb77dc2fd3a863c977d37e67a6a525fdf661917385d569a3ff78e6cae \
    https://huggingface.co/rhasspy/piper-voices/resolve/5041a7a49ae5b3a0f30e6837769eb03fdbb231bd/fa/fa_IR/ganji/medium/fa_IR-ganji-medium.onnx \
    /voices/fa_IR-ganji-medium.onnx
ADD --chmod=644 --checksum=sha256:9d3e0c0cf00156d8bf38fb7f96bdfbcb21911b37e062a328da0632e3c2cbc465 \
    https://huggingface.co/rhasspy/piper-voices/resolve/5041a7a49ae5b3a0f30e6837769eb03fdbb231bd/fa/fa_IR/ganji/medium/fa_IR-ganji-medium.onnx.json \
    /voices/fa_IR-ganji-medium.onnx.json
ADD --chmod=644 --checksum=sha256:e9073b41ae65759dcf95778e569c8f3780406dac99549436f6ab8e7d2336ed72 \
    https://huggingface.co/rhasspy/piper-voices/resolve/5041a7a49ae5b3a0f30e6837769eb03fdbb231bd/fa/fa_IR/ganji_adabi/medium/fa_IR-ganji_adabi-medium.onnx \
    /voices/fa_IR-ganji_adabi-medium.onnx
ADD --chmod=644 --checksum=sha256:aa430ceebaa7c96d9cd6b1e73231a393901cabb23a1b7f53e8d85178a5ae70c9 \
    https://huggingface.co/rhasspy/piper-voices/resolve/5041a7a49ae5b3a0f30e6837769eb03fdbb231bd/fa/fa_IR/ganji_adabi/medium/fa_IR-ganji_adabi-medium.onnx.json \
    /voices/fa_IR-ganji_adabi-medium.onnx.json
ADD --chmod=644 --checksum=sha256:99f0c31464a2120831ca87d079e10a9a2b3e426cc1ee662d80ff9042df15cd3c \
    https://huggingface.co/rhasspy/piper-voices/resolve/5041a7a49ae5b3a0f30e6837769eb03fdbb231bd/fa/fa_IR/reza_ibrahim/medium/fa_IR-reza_ibrahim-medium.onnx \
    /voices/fa_IR-reza_ibrahim-medium.onnx
ADD --chmod=644 --checksum=sha256:e9866c88c16245f8b8f4d0eaeaa6eab4f2e193db69a2ab4683d83fe78a30b6ca \
    https://huggingface.co/rhasspy/piper-voices/resolve/5041a7a49ae5b3a0f30e6837769eb03fdbb231bd/fa/fa_IR/reza_ibrahim/medium/fa_IR-reza_ibrahim-medium.onnx.json \
    /voices/fa_IR-reza_ibrahim-medium.onnx.json
RUN chmod 0755 /voices

COPY hq-common/src /app/hq-common/src
COPY --chmod=0644 tts/voice.lock.json /app/tts/voice.lock.json
COPY --chmod=0644 tts/bakeoff_scripts.json /app/tts/bakeoff_scripts.json
COPY tts/src /app/tts/src

USER 10001
WORKDIR /app/tts
CMD ["python", "-m", "hq_tts"]

# stt: Persian speech to text on the hub's CPU (prompt 06 §3): faster-whisper
# (CTranslate2, int8) with a pinned model read from the stt-models volume.
# The same image runs the one-shot model fetch (python -m hq_stt.fetch).
# Runs as uid 10001 on a read-only root filesystem (compose adds the tmpfs).
FROM python:3.12.15-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/hq-common/src:/app/stt/src \
    HOME=/tmp/home \
    HF_HUB_OFFLINE=1 \
    HF_HUB_DISABLE_TELEMETRY=1 \
    OMP_NUM_THREADS=4

COPY stt/requirements.lock /tmp/requirements.lock
RUN pip install --require-hashes --no-deps -r /tmp/requirements.lock \
    && rm /tmp/requirements.lock \
    && useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin hq \
    && mkdir -p /models && chown 10001:10001 /models

COPY hq-common/src /app/hq-common/src
COPY stt/model.lock.json /app/stt/model.lock.json
COPY stt/src /app/stt/src

USER 10001
WORKDIR /app/stt
EXPOSE 8000
CMD ["python", "-m", "hq_stt"]

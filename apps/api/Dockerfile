# api + worker (apps/api): one image, two entrypoints (python -m hq_api / hq_api.worker).
# Runs as uid 10001 on a read-only root filesystem (compose adds the tmpfs).
# Build context: apps/api, plus the named context "services" for hq-common.
FROM python:3.12.15-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/hq-common/src:/app/api/src

# ffmpeg/ffprobe (LGPL/GPL, Debian trixie, exact version): posters, key frames
# and sound tracks of owner videos, and media durations (prompt 6 §2).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg=7:7.1.5-0+deb13u1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock /tmp/requirements.lock
RUN pip install --require-hashes --no-deps -r /tmp/requirements.lock \
    && rm /tmp/requirements.lock \
    && useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin hq \
    && install -d -o 10001 -g 10001 -m 0700 /data/files

# hadolint ignore=DL3022
COPY --from=services hq-common/src /app/hq-common/src
COPY alembic.ini /app/api/alembic.ini
COPY migrations /app/api/migrations
COPY seed /app/api/seed
COPY openapi /app/api/openapi
COPY src /app/api/src

USER 10001
WORKDIR /app/api
EXPOSE 8000
CMD ["python", "-m", "hq_api"]

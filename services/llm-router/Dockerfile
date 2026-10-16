# llm-router: the single path for every model call (internal only).
# Runs as uid 10001 on a read-only root filesystem (compose adds the tmpfs).
FROM python:3.12.15-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/hq-common/src:/app/llm-router/src

COPY llm-router/requirements.lock /tmp/requirements.lock
RUN pip install --require-hashes --no-deps -r /tmp/requirements.lock \
    && rm /tmp/requirements.lock \
    && useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin hq

COPY hq-common/src /app/hq-common/src
COPY llm-router/alembic.ini /app/llm-router/alembic.ini
COPY llm-router/migrations /app/llm-router/migrations
COPY llm-router/seed /app/llm-router/seed
COPY llm-router/src /app/llm-router/src

USER 10001
WORKDIR /app/llm-router
EXPOSE 8000
CMD ["python", "-m", "llm_router"]

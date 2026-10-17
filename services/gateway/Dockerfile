# Tool Gateway: every action of an agent goes through here (hq-core only).
# Runs as uid 10001 on a read-only root filesystem (compose adds the tmpfs);
# the role charters (agents/) are mounted read-only at /app/agents.
FROM python:3.12.15-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/hq-common/src:/app/gateway/src \
    HQ_AGENTS_DIR=/app/agents

COPY gateway/requirements.lock /tmp/requirements.lock
RUN pip install --require-hashes --no-deps -r /tmp/requirements.lock \
    && rm /tmp/requirements.lock \
    && useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin hq

COPY hq-common/src /app/hq-common/src
COPY gateway/src /app/gateway/src

USER 10001
WORKDIR /app/gateway
EXPOSE 8080
CMD ["python", "-m", "hq_gateway"]

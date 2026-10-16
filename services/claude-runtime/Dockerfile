# claude-runtime: Claude subscription calls via the official Agent SDK
# (bundles Claude Code CLI 2.1.286). Only llm-router can reach it.
# Runs as uid 10001 on a read-only root filesystem (compose adds the tmpfs).
FROM python:3.12.15-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/hq-common/src:/app/claude-runtime/src \
    HOME=/tmp/home \
    CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK=1

COPY claude-runtime/requirements.lock /tmp/requirements.lock
RUN pip install --require-hashes --no-deps -r /tmp/requirements.lock \
    && rm /tmp/requirements.lock \
    && useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin hq

COPY hq-common/src /app/hq-common/src
COPY claude-runtime/src /app/claude-runtime/src

USER 10001
WORKDIR /app/claude-runtime
EXPOSE 8100
CMD ["python", "-m", "claude_runtime"]

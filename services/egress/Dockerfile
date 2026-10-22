# egress (prompt 07 §2): the only service of the hub on a network with a route
# out (hq-egress), for the agents' web tools and MCP servers over HTTP.
# uid 10001, read-only root filesystem (compose adds the tmpfs); no secret of its own.
FROM python:3.12.15-slim-trixie

# glibc: a call's big buffers (a 20 MB body, a browse's base64 files) are
# mmap'd and given back when freed, not kept by a heap that only grows, and
# two malloc arenas (prompt 7.1 §2.20: egress's memory, measured).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/hq-common/src:/app/egress/src \
    MALLOC_MMAP_THRESHOLD_=262144 \
    MALLOC_ARENA_MAX=2

COPY egress/requirements.lock /tmp/requirements.lock
RUN pip install --require-hashes --no-deps -r /tmp/requirements.lock \
    && rm /tmp/requirements.lock \
    && useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin hq

COPY hq-common/src /app/hq-common/src
COPY egress/src /app/egress/src

USER 10001
WORKDIR /app/egress
EXPOSE 8090 3128 3129 3130
CMD ["python", "-m", "hq_egress"]

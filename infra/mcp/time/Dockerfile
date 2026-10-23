# mcp-time (prompt 12 §14.5, contract §21.11): the reference MCP server "time"
# (modelcontextprotocol/servers src/time, MIT) behind mcp-proxy (MIT), which
# serves its stdio over Streamable HTTP on :8080 (/mcp) inside the same image.
# Two venvs: mcp-proxy 0.12.0 runs on mcp 2.x, mcp-server-time 2026.8.18 on
# mcp 1.x. The base is pinned by digest and every package by hash, and the
# build is reproducible (make mcp-build: SOURCE_DATE_EPOCH, rewritten
# timestamps), so the image digest in infra/mcp/servers.yaml is the reviewed
# identity of exactly this file. uid 10001, read-only root, no network but
# hq-mcp (compose).
FROM python:3.12.15-slim-trixie@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/tmp \
    TZ=UTC

COPY time/proxy.lock time/server.lock /tmp/
RUN python -m venv --without-pip /opt/proxy \
    && python -m venv --without-pip /opt/server \
    && pip --python /opt/proxy/bin/python install --no-compile --require-hashes --no-deps -r /tmp/proxy.lock \
    && pip --python /opt/server/bin/python install --no-compile --require-hashes --no-deps -r /tmp/server.lock \
    && rm /tmp/proxy.lock /tmp/server.lock \
    && echo 'hq:x:10001:10001::/nonexistent:/usr/sbin/nologin' >> /etc/passwd \
    && echo 'hq:x:10001:' >> /etc/group

USER 10001
WORKDIR /tmp
EXPOSE 8080
# The same command as infra/mcp/servers.yaml (scripts/quality/infra.sh compares them).
ENTRYPOINT ["/opt/proxy/bin/mcp-proxy", "--host", "0.0.0.0", "--port", "8080", "--", "/opt/server/bin/mcp-server-time", "--local-timezone", "Asia/Tehran"]

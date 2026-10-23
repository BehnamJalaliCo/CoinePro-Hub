# mcp-codecortex (prompt 12 §14.6, contract §21.11): CodeCortex (the owner's own
# project, Apache-2.0, github.com/BehnamJalaliCo/CodeCortex) as a read-only
# "code intelligence" MCP server, behind the same mcp-proxy as mcp-time.
# Its native stdio server (serve.py) over one indexed repository copy; the
# one-shot index job (index.py) is this image too. No `semantic` extra (torch
# does not fit). git (Debian, pinned) for symbol history and PR intelligence.
# Base by digest, packages by hash, reproducible build (make mcp-build), so
# infra/mcp/servers.yaml pins exactly this file. uid 10001, read-only root.
FROM python:3.12.15-slim-trixie@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/tmp \
    TZ=UTC

COPY time/proxy.lock codecortex/server.lock /tmp/
RUN apt-get update \
    && apt-get install -y --no-install-recommends git=1:2.47.3-0+deb13u1 \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/*.bin /var/cache/ldconfig/aux-cache \
              /var/log/apt /var/log/dpkg.log /var/log/alternatives.log \
    && python -m venv --without-pip /opt/proxy \
    && python -m venv --without-pip /opt/server \
    && pip --python /opt/proxy/bin/python install --no-compile --require-hashes --no-deps -r /tmp/proxy.lock \
    && pip --python /opt/server/bin/python install --no-compile --require-hashes --no-deps -r /tmp/server.lock \
    && rm /tmp/proxy.lock /tmp/server.lock \
    && printf '[safe]\n\tdirectory = *\n' > /etc/gitconfig \
    && echo 'hq:x:10001:10001::/nonexistent:/usr/sbin/nologin' >> /etc/passwd \
    && echo 'hq:x:10001:' >> /etc/group \
    && mkdir -p /index/coinepro-hub/.codecortex && chown -R 10001:10001 /index

COPY codecortex/serve.py codecortex/index.py /opt/hq/

USER 10001
WORKDIR /tmp
EXPOSE 8080
# The same command as infra/mcp/servers.yaml (scripts/quality/infra.sh compares them).
ENTRYPOINT ["/opt/proxy/bin/mcp-proxy", "--host", "0.0.0.0", "--port", "8080", "--", "/opt/server/bin/python", "/opt/hq/serve.py", "/index/coinepro-hub"]
